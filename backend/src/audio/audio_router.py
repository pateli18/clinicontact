import json
import logging
from typing import Union

import websockets
from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from src.ai.caller import AiCaller

logger = logging.getLogger(__name__)


class CallRouter:
    stream_sid: Union[str, None]
    last_ai_item_id: Union[str, None]
    mark_queue: list[int]
    mark_queue_elapsed_time: int

    def __init__(self, ai_caller: AiCaller):
        self.stream_sid = None
        self.last_ai_item_id = None
        self.mark_queue = []
        self.mark_queue_elapsed_time = 0
        self.ai_caller = ai_caller
        self._hang_up_requested = False

    async def send_to_human(self, websocket: WebSocket):
        try:
            async for message in self.ai_caller:
                if message["type"] == "response.function_call_arguments.done":
                    if message["name"] == "hang_up":
                        self._hang_up_requested = True
                    else:
                        logger.warning(
                            f"Received unexpected function call: {message['name']}"
                        )

                if message["type"] == "response.audio.delta":
                    audio_delta = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": message["delta"],
                        },
                    }
                    await websocket.send_json(audio_delta)

                    if self.last_ai_item_id is None:
                        self.last_ai_item_id = message["item_id"]
                        self.mark_queue_elapsed_time = 0
                        self.mark_queue.clear()

                    if self.stream_sid is not None:
                        mark_event = {
                            "event": "mark",
                            "streamSid": self.stream_sid,
                            "mark": {"name": "responsePart"},
                        }
                        await websocket.send_json(mark_event)
                        self.mark_queue.append(message["audio_ms"])

                if message["type"] == "input_audio_buffer.speech_started":
                    await self.handle_speech_started(websocket)
        except Exception:
            logger.exception("Error sending to human")
        finally:
            await self.ai_caller.close()
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
            logger.info("Closed connection to human")

    async def handle_speech_started(self, websocket: WebSocket):
        if len(self.mark_queue) > 0:
            if self.last_ai_item_id is not None:
                await self.ai_caller.truncate_message(
                    self.last_ai_item_id, self.mark_queue_elapsed_time
                )

            await websocket.send_json(
                {"event": "clear", "streamSid": self.stream_sid}
            )

            self.mark_queue.clear()
        self.last_ai_item_id = None
        self.mark_queue_elapsed_time = 0

    async def receive_from_human_call(self, websocket: WebSocket):
        try:
            async for message in websocket.iter_text():
                data = json.loads(message)
                if data["event"] == "media":
                    await self.ai_caller.receive_human_audio(
                        data["media"]["payload"]
                    )
                elif data["event"] == "start":
                    self.stream_sid = data["start"]["streamSid"]
                    self.last_ai_item_id = None
                    self.mark_queue_elapsed_time = 0
                    self.mark_queue.clear()
                elif data["event"] == "mark":
                    if self.mark_queue:
                        time_ms = self.mark_queue.pop(0)
                        self.mark_queue_elapsed_time += time_ms
                        if (
                            self._hang_up_requested
                            and len(self.mark_queue) == 0
                        ):
                            logger.info(
                                "Hang up requested and all media processed"
                            )
                            break
        except websockets.exceptions.ConnectionClosedOK:
            logger.info("Connection closed")
        except Exception:
            logger.exception("Error receiving from human")
        finally:
            await self.ai_caller.close()
            logger.info("Closed connection to bot")


class BrowserRouter:
    last_ai_item_id: Union[str, None]
    mark_queue: list[int]
    mark_queue_elapsed_time: int

    def __init__(self, ai_caller: AiCaller):
        self.last_ai_item_id = None
        self.mark_queue = []
        self.mark_queue_elapsed_time = 0
        self.ai_caller = ai_caller
        self._hang_up_requested = False

    async def send_to_human(self, websocket: WebSocket):
        try:
            async for message in self.ai_caller:
                if message["type"] == "response.function_call_arguments.done":
                    if message["name"] == "hang_up":
                        self._hang_up_requested = True
                    else:
                        logger.warning(
                            f"Received unexpected function call: {message['name']}"
                        )

                if message["type"] == "response.audio.delta":
                    await websocket.send_json(
                        {"event": "media", "payload": message["delta"]}
                    )

                    if self.last_ai_item_id is None:
                        self.last_ai_item_id = message["item_id"]
                        self.mark_queue_elapsed_time = 0
                        self.mark_queue.clear()
                    self.mark_queue.append(message["audio_ms"])

                if message["type"] == "input_audio_buffer.speech_started":
                    await self.handle_speech_started(websocket)
        except Exception:
            logger.exception("Error sending to human")
        finally:
            await self.ai_caller.close()
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
            logger.info("Closed connection to human")

    async def handle_speech_started(self, websocket: WebSocket):
        if len(self.mark_queue) > 0:
            if self.last_ai_item_id is not None:
                await self.ai_caller.truncate_message(
                    self.last_ai_item_id, self.mark_queue_elapsed_time
                )

            await websocket.send_json({"event": "clear"})

            self.mark_queue.clear()
        self.last_ai_item_id = None
        self.mark_queue_elapsed_time = 0

    async def receive_from_human_call(self, websocket: WebSocket):
        try:
            async for message in websocket.iter_text():
                data = json.loads(message)
                if data["event"] == "media":
                    await self.ai_caller.receive_human_audio(data["payload"])
                elif data["event"] == "start":
                    logger.info("Incoming stream has started")
                    self.last_ai_item_id = None
                    self.mark_queue_elapsed_time = 0
                    self.mark_queue.clear()
                elif data["event"] == "mark":
                    if self.mark_queue:
                        time_ms = self.mark_queue.pop(0)
                        self.mark_queue_elapsed_time += time_ms
                        if (
                            self._hang_up_requested
                            and len(self.mark_queue) == 0
                        ):
                            logger.info(
                                "Hang up requested and all media processed"
                            )
                            break
        except websockets.exceptions.ConnectionClosedOK:
            logger.info("Connection closed")
        except Exception:
            logger.exception("Error receiving from human")
        finally:
            await self.ai_caller.close()
            logger.info("Closed connection to bot")
