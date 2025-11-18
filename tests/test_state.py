from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from agents.utils.state import get_agent_snapshot


def _session(state=None, events=None):
    return SimpleNamespace(state=state or {}, events=events or [])


def test_returns_cached_snapshot():
    session = _session(state={"agent_snapshots": {"AgentA": {"foo": "bar"}}})

    snapshot = get_agent_snapshot(session, "AgentA")

    assert snapshot == {"foo": "bar"}


def test_parses_json_embedded_in_agent_responses():
    state = {
        "agent_responses": {
            "IncidentDetectionAgent": [
                "Here is the incident report:\n```json\n{\"incident_detected\": true}\n```"
            ]
        }
    }
    session = _session(state=state)

    snapshot = get_agent_snapshot(session, "IncidentDetectionAgent")

    assert snapshot["incident_detected"] is True
    assert session.state["agent_snapshots"]["IncidentDetectionAgent"] == snapshot


def test_falls_back_to_events_when_responses_missing():
    event = SimpleNamespace(
        author="IncidentDetectionAgent",
        actions=SimpleNamespace(agent_state=None),
        content=SimpleNamespace(
            parts=[SimpleNamespace(text="Summary:\n{\"incident_detected\": false}")]
        ),
    )
    session = _session(events=[event])

    snapshot = get_agent_snapshot(session, "IncidentDetectionAgent")

    assert snapshot["incident_detected"] is False

