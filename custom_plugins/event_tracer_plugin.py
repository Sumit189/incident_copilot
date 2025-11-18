from __future__ import annotations
import json
import logging
from datetime import datetime

from google.adk.plugins import BasePlugin
from motor.motor_asyncio import AsyncIOMotorClient


def iso_now():
    return datetime.utcnow().isoformat() + "Z"


class EventTracerPlugin(BasePlugin):
    """
    Clean, minimal, easy-to-read event tracer for ADK.
    Stores all events for debugging or audit.
    """

    def __init__(self, mongo_uri=None, db_name=None, coll_name=None):
        super().__init__("event_tracer")

        if mongo_uri and db_name and coll_name:
            client = AsyncIOMotorClient(mongo_uri)
            self.collection = client[db_name][coll_name]
            logging.info("[EventTracerPlugin] Mongo enabled")
        else:
            self.collection = None
            logging.info("[EventTracerPlugin] Mongo disabled")

    # ------------------------------
    # Safe for JSON
    # ------------------------------
    def safe(self, value):
        try:
            json.dumps(value)
            return value
        except:
            return str(value)

    # ------------------------------
    # Extract readable text
    # ------------------------------
    def extract_text(self, event):
        content = getattr(event, "content", None)
        if not content:
            return None

        try:
            for part in content.parts:
                t = getattr(part, "text", None)
                if t and isinstance(t, str):
                    return t.strip()
        except:
            pass

        return None

    # ------------------------------
    # Event serializer
    # ------------------------------
    def serialize_event(self, ev):
        # tool calls
        try:
            calls = ev.get_function_calls() or []
        except:
            calls = []

        # tool responses
        try:
            results = ev.get_function_responses() or []
        except:
            results = []

        actions = getattr(ev, "actions", None)

        # determine type
        if getattr(ev, "author", None) == "user":
            etype = "user_message"
        elif calls:
            etype = "tool_call"
        elif results:
            etype = "tool_result"
        elif actions and (actions.state_delta or actions.artifact_delta):
            etype = "state_update"
        elif actions and (actions.transfer_to_agent or actions.escalate):
            etype = "control_signal"
        elif hasattr(ev, "is_final_response") and ev.is_final_response():
            etype = "final_output"
        else:
            etype = "agent_output"

        return {
            "id": getattr(ev, "id", None),
            "timestamp": iso_now(),
            "author": getattr(ev, "author", None),
            "type": etype,
            "text": self.extract_text(ev),

            "function_calls": [
                {"name": c.name, "args": self.safe(getattr(c, "args", None))}
                for c in calls
            ] or None,

            "function_responses": [
                {"name": r.name, "response": self.safe(getattr(r, "response", None))}
                for r in results
            ] or None,

            "state_delta": self.safe(actions.state_delta) if actions else None,
            "artifact_delta": self.safe(actions.artifact_delta) if actions else None,

            "control": {
                "transfer_to_agent": getattr(actions, "transfer_to_agent", None) if actions else None,
                "escalate": getattr(actions, "escalate", None) if actions else None,
                "skip_summarization": getattr(actions, "skip_summarization", None) if actions else None,
            },

            "raw_content": self.safe(getattr(ev, "content", None)),
            "raw_actions": self.safe(actions),
        }

    # ------------------------------
    # User message logging
    # ------------------------------
    async def on_user_message_callback(self, *, invocation_context, user_message):
        if self.collection is None:
            return

        await self.collection.update_one(
            {"invocation_id": invocation_context.invocation_id},
            {
                "$setOnInsert": {
                    "invocation_id": invocation_context.invocation_id,
                    "session_id": getattr(invocation_context.session, "id", None),
                    "created_at": iso_now(),
                },
                "$set": {
                    "user_input": str(user_message),
                    "updated_at": iso_now(),
                }
            },
            upsert=True,
        )

    # ------------------------------
    # After agent → save all events
    # ------------------------------
    async def after_agent_callback(self, *, agent, callback_context):
        if self.collection is None:
            return

        session = getattr(callback_context, "session", None)
        if not session:
            return

        events = getattr(session, "events", []) or []
        invocation_id = callback_context.invocation_id

        serialized = [
            self.serialize_event(ev)
            for ev in events
            if getattr(ev, "invocation_id", None) == invocation_id
        ]

        trace = {
            "agent": agent.name,
            "run_start": iso_now(),
            "run_end": iso_now(),
            "events": serialized,
        }

        await self.collection.update_one(
            {"invocation_id": invocation_id},
            {
                "$set": {
                    f"traces.{agent.name}": trace,
                    "updated_at": iso_now(),
                }
            },
            upsert=True,
        )

        logging.info(
            f"[EventTracerPlugin] Stored {len(serialized)} events for {agent.name}"
        )
