from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union, cast
from uuid import UUID

from pydantic import BaseModel, PlainSerializer, model_serializer

SerializedUUID = Annotated[
    UUID, PlainSerializer(lambda x: str(x), return_type=str)
]
SerializedDateTime = Annotated[
    datetime, PlainSerializer(lambda x: x.isoformat(), return_type=str)
]


class ModelChatType(str, Enum):
    developer = "developer"
    system = "system"
    user = "user"
    assistant = "assistant"


class ModelChatContentImageDetail(str, Enum):
    low = "low"
    auto = "auto"
    high = "high"


class ModelChatContentImage(BaseModel):
    url: str
    detail: ModelChatContentImageDetail

    @classmethod
    def from_b64(
        cls,
        b64_image: str,
        detail: ModelChatContentImageDetail = ModelChatContentImageDetail.auto,
    ) -> "ModelChatContentImage":
        return cls(url=f"data:image/png;base64,{b64_image}", detail=detail)


class ModelChatContentType(str, Enum):
    text = "text"
    image_url = "image_url"


SerializedModelChatContent = dict[str, Union[str, dict]]


class ModelChatContent(BaseModel):
    type: ModelChatContentType
    content: Union[str, ModelChatContentImage]

    @model_serializer
    def serialize(self) -> SerializedModelChatContent:
        content_key = self.type.value
        content_value = (
            self.content
            if isinstance(self.content, str)
            else self.content.model_dump()
        )
        return {"type": self.type.value, content_key: content_value}

    @classmethod
    def from_serialized(
        cls, data: SerializedModelChatContent
    ) -> "ModelChatContent":
        type_ = ModelChatContentType(data["type"])
        content_key = type_.value
        content_value = data[content_key]
        if type_ == ModelChatContentType.image_url:
            content = ModelChatContentImage(**cast(dict, content_value))
        else:
            content = cast(str, content_value)
        return cls(type=type_, content=content)


class ModelChat(BaseModel):
    role: ModelChatType
    content: Union[str, list[ModelChatContent]]

    @classmethod
    def from_b64_image(
        cls, role: ModelChatType, b64_image: str
    ) -> "ModelChat":
        return cls(
            role=role,
            content=[
                ModelChatContent(
                    type=ModelChatContentType.image_url,
                    content=ModelChatContentImage.from_b64(b64_image),
                )
            ],
        )

    @classmethod
    def from_serialized(
        cls, data: dict[str, Union[str, list[SerializedModelChatContent]]]
    ) -> "ModelChat":
        role = ModelChatType(data["role"])
        if isinstance(data["content"], str):
            return cls(role=role, content=cast(str, data["content"]))
        else:
            content = [
                ModelChatContent.from_serialized(content_data)
                for content_data in data["content"]
            ]
            return cls(role=role, content=content)


class ToolChoiceFunction(BaseModel):
    name: str


class ToolChoiceObject(BaseModel):
    type: str = "function"
    function: ToolChoiceFunction


ToolChoice = Optional[Union[Literal["auto"], ToolChoiceObject]]


class ModelType(str, Enum):
    gpto1 = "o1-preview"
    gpt4o = "gpt-4o"
    claude35 = "claude-3-5-sonnet-20241022"
    realtime = "gpt-4o-realtime-preview-2024-12-17"


class ModelFunction(BaseModel):
    name: str
    description: Optional[str]
    parameters: Optional[dict]


class Tool(BaseModel):
    type: str = "function"
    function: ModelFunction


class ResponseType(BaseModel):
    type: Literal["json_object"] = "json_object"


class StreamOptions(BaseModel):
    include_usage: bool


class OpenAiChatInput(BaseModel):
    messages: list[ModelChat]
    model: ModelType
    max_completion_tokens: Optional[int] = None
    n: int = 1
    temperature: float = 0.0
    stop: Optional[str] = None
    tools: Optional[list[Tool]] = None
    tool_choice: ToolChoice = None
    stream: bool = False
    logprobs: bool = False
    top_logprobs: Optional[int] = None
    response_format: Optional[ResponseType] = None
    stream_options: Optional[StreamOptions] = None

    @property
    def data(self) -> dict:
        exclusion = set()
        if self.tools is None:
            exclusion.add("tools")
        if self.tool_choice is None:
            exclusion.add("tool_choice")
        if self.stream is True:
            self.stream_options = StreamOptions(include_usage=True)
        if self.model == ModelType.gpto1:
            exclusion.add("temperature")
            exclusion.add("stop")
        output = self.model_dump(
            exclude=exclusion,
        )
        if self.model == ModelType.claude35:
            output["max_tokens"] = self.max_completion_tokens or 8192
            del output["max_completion_tokens"]
            del output["n"]
            del output["stop"]
            del output["logprobs"]
            del output["top_logprobs"]
            del output["response_format"]
            del output["stream_options"]
        return output


class PhoneCallStatus(str, Enum):
    queued = "queued"
    ringing = "ringing"
    in_progress = "in-progress"
    completed = "completed"
    busy = "busy"
    failed = "failed"
    no_answer = "no-answer"


class PhoneCallMetadata(BaseModel):
    id: SerializedUUID
    from_phone_number: str
    to_phone_number: str
    input_data: dict
    status: PhoneCallStatus
    created_at: SerializedDateTime
    duration: Optional[int] = None
    recording_available: bool


class Speaker(str, Enum):
    user = "User"
    assistant = "Assistant"


class SpeakerSegment(BaseModel):
    timestamp: float
    speaker: Speaker
    transcript: str
    item_id: str


class BarHeight(BaseModel):
    height: float
    speaker: Speaker
