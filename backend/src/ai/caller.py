import asyncio
import base64
import json
import logging
import os
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import (
    AsyncContextManager,
    AsyncIterator,
    Literal,
    Optional,
    Sequence,
    Union,
)

import aiofiles
import websockets
from pydantic import BaseModel, Field
from pydantic.json import pydantic_encoder

from src.ai.prompts import hang_up_tool
from src.aws_utils import S3Client
from src.db.api import update_phone_call
from src.db.base import async_session_scope
from src.helixion_types import (
    CALL_END_EVENT,
    AiMessageMetadataEventTypes,
    AudioFormat,
    ModelType,
    SerializedUUID,
    Speaker,
    SpeakerSegment,
    Voice,
)
from src.settings import settings

logger = logging.getLogger(__name__)


def _format_user_info(user_info: dict) -> str:
    user_info_fmt = ""
    for key, value in user_info.items():
        user_info_fmt += f"\t-{key}: {value}\n"
    return user_info_fmt


class TurnDetection(BaseModel):
    type: Literal["server_vad"] = "server_vad"
    threshold: float = 0.5  # 0-1, higher is for noisier audio
    prefix_padding_ms: int = 300
    silence_duration_ms: int = 500


class AiSessionConfiguration(BaseModel):
    turn_detection: Optional[TurnDetection]
    input_audio_format: Optional[AudioFormat]
    output_audio_format: Optional[AudioFormat]
    voice: Optional[Voice]
    instructions: Optional[str]
    input_audio_transcription: Optional[dict]
    tools: list[dict] = Field(default_factory=list)

    @classmethod
    def default(
        cls,
        system_prompt: str,
        user_info: dict,
        audio_format: AudioFormat,
        include_hang_up_tool: bool,
    ) -> "AiSessionConfiguration":
        user_info_fmt = _format_user_info(user_info)
        system_message = system_prompt.format(user_info=user_info_fmt)

        tools = []
        if include_hang_up_tool:
            tools.append(hang_up_tool)

        return cls(
            turn_detection=TurnDetection(),
            input_audio_format=audio_format,
            output_audio_format=audio_format,
            voice="shimmer",
            instructions=system_message,
            tools=tools,
            input_audio_transcription={
                "model": "whisper-1",
            },
        )


class AiMessageQueues:
    audio_queue: asyncio.Queue[str]
    metadata_queue: asyncio.Queue[str]

    def __init__(self):
        self.audio_queue = asyncio.Queue()
        self.metadata_queue = asyncio.Queue()

    def add_audio(self, audio: str):
        self.audio_queue.put_nowait(audio)

    def add_metadata(
        self,
        event_type: AiMessageMetadataEventTypes,
        event_data: Union[BaseModel, None, Sequence[BaseModel]],
    ):
        self.metadata_queue.put_nowait(
            json.dumps(
                {"type": event_type.value, "data": event_data},
                default=pydantic_encoder,
            )
        )

    def end_call(self):
        self.audio_queue.put_nowait(CALL_END_EVENT)

        self.add_metadata(
            AiMessageMetadataEventTypes.call_end,
            None,
        )


class AiCaller(AsyncContextManager["AiCaller"]):
    def __init__(
        self,
        user_info: dict,
        system_prompt: str,
        phone_call_id: SerializedUUID,
        message_queues: Optional[AiMessageQueues],
        audio_format: AudioFormat = "g711_ulaw",
    ):
        self._exit_stack = AsyncExitStack()
        self._ws_client = None
        self._log_file: Optional[str] = None
        self.session_configuration = AiSessionConfiguration.default(
            system_prompt, user_info, audio_format, True
        )
        self._sampling_rate = 24000 if audio_format == "pcm16" else 8000
        self._log_tasks: list[asyncio.Task] = []
        self._cleanup_started = False
        self._phone_call_id = phone_call_id
        self._message_queues = message_queues
        self._audio_input_buffer_ms: int = (
            self.session_configuration.turn_detection.prefix_padding_ms
            if self.session_configuration.turn_detection
            else 0
        )
        self._audio_total_buffer_ms: int = 0
        self._audio_input_buffer: list[tuple[str, int, int]] = []
        self._user_speaking: bool = False
        self._speaker_segments: list[SpeakerSegment] = []

    async def __aenter__(self) -> "AiCaller":
        self._ws_client = await self._exit_stack.enter_async_context(
            websockets.connect(
                f"wss://api.openai.com/v1/realtime?model={ModelType.realtime.value}",
                additional_headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "OpenAI-Beta": "realtime=v1",
                },
            )
        )
        await self.initialize_session()
        self._log_file = f"logs/{self._phone_call_id}.log"
        logger.info(f"Initialized session with {self._log_file=}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._exit_stack.__aexit__(exc_type, exc, tb)
        await self.close()

    @property
    def client(self):
        if not self._ws_client:
            raise RuntimeError("WebSocket client not initialized")
        return self._ws_client

    @property
    def log_file(self) -> str:
        if not self._log_file:
            raise RuntimeError("Log file not initialized")
        Path(self._log_file).parent.mkdir(parents=True, exist_ok=True)
        return self._log_file

    async def initialize_session(self):
        session_update = {
            "type": "session.update",
            "session": self.session_configuration.model_dump(),
        }
        await self.send_message(json.dumps(session_update))

    async def _log_message(self, message: websockets.Data):
        # Ensure log directory exists
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}\n"
        try:
            async with aiofiles.open(self.log_file, mode="a") as f:
                await f.write(log_entry)
        except Exception:
            logger.exception("Error writing to log file")

    def _update_speaker_segments(self, speaker_segment: SpeakerSegment):
        # check if the speaker segment exists in the list
        found = False
        for segment in self._speaker_segments:
            if segment.item_id == speaker_segment.item_id:
                segment.transcript = speaker_segment.transcript
                found = True
                break

        if not found:
            self._speaker_segments.append(speaker_segment)

        if self._message_queues is not None:
            self._message_queues.add_metadata(
                AiMessageMetadataEventTypes.speaker,
                self._speaker_segments,
            )

    async def send_message(self, message: str) -> None:
        await self.client.send(message)
        task = asyncio.create_task(self._log_message(message))
        self._log_tasks.append(task)

    async def truncate_message(self, item_id: str, audio_end_ms: int):
        truncate_event = {
            "type": "conversation.item.truncate",
            "item_id": item_id,
            "content_index": 0,
            "audio_end_ms": audio_end_ms,
        }
        await self.send_message(json.dumps(truncate_event))

    def _audio_ms(self, audio_b64: str) -> int:
        audio_bytes = base64.b64decode(audio_b64)
        return int((len(audio_bytes) / 2) * 1000 / self._sampling_rate)

    async def receive_human_audio(self, audio: str):
        audio_append = {
            "type": "input_audio_buffer.append",
            "audio": audio,
        }
        await self.send_message(json.dumps(audio_append))

        # update full message tracker size
        audio_ms = self._audio_ms(audio)
        self._audio_input_buffer_ms += audio_ms

        # either dump to streaming queue or input buffer
        if self._user_speaking:
            self._audio_total_buffer_ms += audio_ms
            if self._message_queues is not None:
                self._message_queues.add_audio(audio)
        else:
            self._audio_input_buffer.append(
                (audio, audio_ms, self._audio_input_buffer_ms)
            )

    async def _message_handler(self, message: websockets.Data) -> dict:
        asyncio.create_task(self._log_message(message))

        response = json.loads(message)

        if response["type"] == "input_audio_buffer.speech_started":
            self._user_speaking = True
            self._update_speaker_segments(
                SpeakerSegment(
                    timestamp=self._audio_total_buffer_ms / 1000,
                    speaker=Speaker.user,
                    transcript="",
                    item_id=response["item_id"],
                )
            )
            audio_start_ms = response["audio_start_ms"]
            for audio, individual_ms, ms in self._audio_input_buffer:
                if ms >= audio_start_ms:
                    self._audio_total_buffer_ms += individual_ms
                    if self._message_queues is not None:
                        self._message_queues.add_audio(audio)
            self._audio_input_buffer = []
        elif response["type"] == "input_audio_buffer.speech_stopped":
            self._user_speaking = False
            self._update_speaker_segments(
                SpeakerSegment(
                    timestamp=self._audio_total_buffer_ms / 1000,
                    speaker=Speaker.assistant,
                    transcript="",
                    item_id="",
                ),
            )
        elif response["type"] == "response.audio.delta":
            audio_ms = self._audio_ms(response["delta"])
            response["audio_ms"] = audio_ms  # add so that caller can use
            self._audio_total_buffer_ms += audio_ms
            if self._message_queues is not None:
                self._message_queues.add_audio(response["delta"])
            if (
                len(self._speaker_segments) > 0
                and self._speaker_segments[-1].item_id == ""
            ):
                self._speaker_segments[-1].item_id = response["item_id"]
        elif (
            response["type"]
            == "conversation.item.input_audio_transcription.completed"
        ):
            self._update_speaker_segments(
                SpeakerSegment(
                    timestamp=0,  # this value is not used
                    speaker=Speaker.user,
                    transcript=response["transcript"],
                    item_id=response["item_id"],
                ),
            )
        elif response["type"] == "response.audio_transcript.done":
            self._update_speaker_segments(
                SpeakerSegment(
                    timestamp=0,  # this value is not used
                    speaker=Speaker.assistant,
                    transcript=response["transcript"],
                    item_id=response["item_id"],
                ),
            )

        return response

    async def close(self) -> tuple[SerializedUUID, int]:
        if self._cleanup_started:
            logger.info("Cleanup already started")
            return self._phone_call_id, self._audio_total_buffer_ms
        self._cleanup_started = True

        if self._ws_client is not None:
            await self._ws_client.close()

        # close the queues
        if self._message_queues is not None:
            self._message_queues.end_call()

        if len(self._log_tasks) > 0:
            logger.info(f"Flushing {len(self._log_tasks)} log tasks")
            await asyncio.gather(*self._log_tasks, return_exceptions=True)
        async with S3Client() as s3_client:
            async with aiofiles.open(self.log_file, mode="rb") as f:
                data = await f.read()
            s3_filepath = f"s3://clinicontact/{self.log_file}"
            await s3_client.upload_file(data, s3_filepath, "text/plain")

        async with async_session_scope() as db:
            await update_phone_call(
                self._phone_call_id,
                s3_filepath,
                db,
            )
        # delete the file
        os.remove(self.log_file)
        self._log_tasks.clear()
        self._log_file = None
        return self._phone_call_id, self._audio_total_buffer_ms

    async def __aiter__(self) -> AsyncIterator[dict]:
        while True:
            try:
                message = await self.client.recv()
                processed_message = await self._message_handler(message)
                yield processed_message
            except websockets.exceptions.ConnectionClosed:
                logger.info("Connection closed to openai")
                return
