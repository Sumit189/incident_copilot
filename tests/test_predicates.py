import pytest
from unittest.mock import MagicMock
from agents.utils.predicates import is_incident_confirmed, is_code_issue, is_patch_ready

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.session.state = {}
    return ctx

def test_is_incident_confirmed_true(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "IncidentDetectionAgent": [{
                "incident_detected": True,
                "recommendation": "proceed"
            }]
        }
    }
    assert is_incident_confirmed(mock_ctx) is True

def test_is_incident_confirmed_false_no_incident(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "IncidentDetectionAgent": [{
                "incident_detected": False,
                "recommendation": "proceed"
            }]
        }
    }
    assert is_incident_confirmed(mock_ctx) is False

def test_is_incident_confirmed_false_skip(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "IncidentDetectionAgent": [{
                "incident_detected": True,
                "recommendation": "skip"
            }]
        }
    }
    assert is_incident_confirmed(mock_ctx) is False

def test_is_code_issue_true(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "IncidentDetectionAgent": [{
                "incident_type_hint": "code_issue"
            }]
        }
    }
    assert is_code_issue(mock_ctx) is True

def test_is_code_issue_false(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "IncidentDetectionAgent": [{
                "incident_type_hint": "infrastructure_issue"
            }]
        }
    }
    assert is_code_issue(mock_ctx) is False

def test_is_patch_ready_true(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "SolutionGeneratorAgent": [{
                "patch": {
                    "files_to_modify": [
                        {"proposed_code": "some code"}
                    ]
                }
            }]
        }
    }
    assert is_patch_ready(mock_ctx) is True

def test_is_patch_ready_false_no_patch(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "SolutionGeneratorAgent": [{}]
        }
    }
    assert is_patch_ready(mock_ctx) is False

def test_is_patch_ready_false_no_code(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "SolutionGeneratorAgent": [{
                "patch": {
                    "files_to_modify": [
                        {"proposed_code": ""}
                    ]
                }
            }]
        }
    }
    assert is_patch_ready(mock_ctx) is False

def test_is_patch_ready_false_list_snapshot(mock_ctx):
    mock_ctx.session.state = {
        "agent_responses": {
            "SolutionGeneratorAgent": [
                {"patch": {}}
            ]
        }
    }
    # get_agent_snapshot might return the list directly if it parses it that way
    # We simulate the scenario where get_agent_snapshot returns a list
    # But since we are mocking ctx, we need to ensure get_agent_snapshot returns what we expect
    # The real get_agent_snapshot logic is complex, but here we are testing the predicate.
    # So we should mock get_agent_snapshot or set up the state such that the predicate receives a list.
    # However, the predicate calls get_agent_snapshot.
    # Let's rely on the fact that we are testing the predicate logic given a return value.
    # But wait, the predicate calls get_agent_snapshot internally.
    # We can't easily mock get_agent_snapshot here without patching it.
    # Instead, let's assume the state setup causes get_agent_snapshot to return a list.
    # Based on state.py: if entry is a list, it returns it.
    pass 

# Re-writing the test to actually patch get_agent_snapshot for precise control
from unittest.mock import patch

@patch('agents.utils.predicates.get_agent_snapshot')
def test_is_patch_ready_false_list_snapshot(mock_get_snapshot, mock_ctx):
    mock_get_snapshot.return_value = [{"some": "list"}]
    assert is_patch_ready(mock_ctx) is False
