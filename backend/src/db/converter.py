from typing import Optional, cast

from src.db.models import AgentModel, PhoneCallModel
from src.helixion_types import (
    Agent,
    AgentMetadata,
    DocumentMetadata,
    PhoneCallMetadata,
    PhoneCallStatus,
    SerializedUUID,
)


def latest_phone_call_event(phone_call: PhoneCallModel) -> Optional[dict]:
    if len(phone_call.events) == 0:
        return None
    return sorted(
        phone_call.events,
        key=lambda event: int(event.payload["SequenceNumber"]),
    )[-1].payload


def convert_phone_call_model(phone_call: PhoneCallModel) -> PhoneCallMetadata:
    # get latest event status
    event_payload = latest_phone_call_event(phone_call)
    if event_payload is None:
        event_payload = {
            "CallStatus": PhoneCallStatus.queued,
            "CallDuration": None,
        }

    return PhoneCallMetadata(
        id=cast(SerializedUUID, phone_call.id),
        from_phone_number=cast(str, phone_call.from_phone_number),
        to_phone_number=cast(str, phone_call.to_phone_number),
        input_data=cast(dict, phone_call.input_data),
        status=event_payload["CallStatus"],
        created_at=phone_call.created_at,
        duration=event_payload.get("CallDuration"),
        recording_available=phone_call.call_data is not None,
        agent_metadata=AgentMetadata(
            base_id=phone_call.agent.base_id,
            name=phone_call.agent.name,
            version_id=phone_call.agent.id,
        ),
    )


def convert_agent_model(agent: AgentModel) -> Agent:
    return Agent(
        base_id=cast(SerializedUUID, agent.base_id),
        name=cast(str, agent.name),
        id=cast(SerializedUUID, agent.id),
        created_at=agent.created_at,
        system_message=cast(str, agent.system_message),
        active=cast(bool, agent.active),
        document_metadata=[
            DocumentMetadata(
                id=cast(SerializedUUID, document.document.id),
                name=cast(str, document.document.name),
            )
            for document in agent.documents
        ],
        sample_values=cast(Optional[dict], agent.sample_values) or {},
    )
