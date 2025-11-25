import pathlib
import sys
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ensure_base_plugin():
    try:
        import google.adk.plugins  # noqa: F401
        return
    except ModuleNotFoundError:
        google_module = types.ModuleType("google")
        adk_module = types.ModuleType("google.adk")
        plugins_module = types.ModuleType("google.adk.plugins")

        class _BasePlugin:  # minimal stub for tests
            pass

        plugins_module.BasePlugin = _BasePlugin
        google_module.adk = adk_module
        adk_module.plugins = plugins_module

        sys.modules["google"] = google_module
        sys.modules["google.adk"] = adk_module
        sys.modules["google.adk.plugins"] = plugins_module


_ensure_base_plugin()

from custom_plugins.event_tracer_plugin import EventTracerPlugin  # noqa: E402


class DummyEvent:
    def __init__(self, invocation_id, author):
        self.invocation_id = invocation_id
        self.author = author


def test_get_agent_events_filters_by_author_and_invocation():
    plugin = EventTracerPlugin()

    events = [
        DummyEvent("inv-a", "IncidentDetectionAgent"),
        DummyEvent("inv-a", "SuggestionAgent"),
        DummyEvent("inv-b", "SuggestionAgent"),
    ]

    filtered = plugin._get_agent_events(events, "inv-a", "SuggestionAgent")

    assert len(filtered) == 1
    assert filtered[0].author == "SuggestionAgent"


def test_get_agent_events_returns_empty_when_no_match():
    plugin = EventTracerPlugin()
    events = [DummyEvent("inv-a", "IncidentDetectionAgent")]

    assert plugin._get_agent_events(events, "inv-a", "RCAAgent") == []

