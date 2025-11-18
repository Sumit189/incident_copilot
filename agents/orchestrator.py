import logging
import os
import json
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai import types
from agents.agent import app
from agents.utils.state import get_agent_snapshot

from tools.email_helper import (
    reset_email_status,
    was_email_sent,
    get_last_email_status,
)

logger = logging.getLogger("incident_copilot.orchestrator")

from agents.config import APP_NAME, LOOKUP_WINDOW_SECONDS


session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

runner = Runner(
    app=app,
    session_service=session_service,
    memory_service=memory_service,
)


def _normalize_iso8601(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("end_time must be an ISO-8601 string") from exc


def _format_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def run_workflow(
    user_id: str,
    service_name: str,
    end_time: Optional[str] = None,
    lookup_window_seconds: Optional[int] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:

    reset_email_status()

    if not service_name or not service_name.strip():
        raise ValueError("service_name is required")

    if lookup_window_seconds is None:
        lookup_window_seconds = LOOKUP_WINDOW_SECONDS

    end_dt = _normalize_iso8601(end_time) if end_time else datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(seconds=lookup_window_seconds)

    start_time = _format_iso(start_dt)
    normalized_end_time = _format_iso(end_dt)

    payload = {
        "service_name": service_name,
        "lookup_window_seconds": lookup_window_seconds,
    }
    content = types.Content(parts=[types.Part(text=json.dumps(payload))], role="user")

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=f"incident_{uuid.uuid4().hex[:8]}",
    )

    session.state.setdefault("agent_responses", {})

    events = []
    all_responses = []
    status = "completed"
    error = None

    try:
        coro = app.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        )

        async def collect():
            async for event in coro:
                events.append(event)
                if getattr(event, "content", None):
                    for part in event.content.parts or []:
                        if getattr(part, "text", None):
                            all_responses.append(part.text)
                if getattr(event, "is_final_response", lambda: False)():
                    break

        await asyncio.wait_for(collect(), timeout=timeout_seconds)

    except asyncio.TimeoutError:
        status = "timeout"
        error = f"Timeout after {timeout_seconds}s"
    except Exception as exc:
        status = "failed"
        error = str(exc)

    incident_snapshot = get_agent_snapshot(session, "IncidentDetectionAgent") or {}
    incident_detected = bool(incident_snapshot.get("incident_detected"))

    if incident_detected and not was_email_sent():
        raise RuntimeError("EmailWriterAgent completed without calling send_incident_email_to_oncall.")

    try:
        await memory_service.add_session_to_memory(session)
    except Exception:
        pass

    output = {
        "incident_id": session.id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input": {
            "user_id": user_id,
            "service_name": service_name,
            "start_time": start_time,
            "end_time": normalized_end_time,
            "lookup_window_seconds": lookup_window_seconds,
        },
        "incident_detected": incident_detected,
        "status": status,
        "error": error,
        "agent_responses": session.state["agent_responses"],
        "all_responses": all_responses,
        "email_delivery": {
            "agent_triggered": was_email_sent(),
            "last_status": get_last_email_status(),
        },
        "events_count": len(events),
    }

    from agents.config import SAVE_OUTPUT
    if SAVE_OUTPUT:
    os.makedirs("output", exist_ok=True)
    fn = f"output/incident_{session.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output
