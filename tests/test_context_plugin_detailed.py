import pytest
from unittest.mock import MagicMock, patch
from google.genai import types
from custom_plugins.context_injection_plugin import ContextInjectionPlugin

@pytest.mark.asyncio
async def test_context_injection_detailed():
    plugin = ContextInjectionPlugin()
    
    # Mock agent and callback context
    agent = MagicMock()
    agent.name = "PostProcessAgent"
    
    mock_session = MagicMock()
    callback_context = MagicMock()
    callback_context.session = mock_session
    callback_context.input = types.Content(parts=[types.Part(text="Generate report")])
    
    # Mock get_agent_snapshot to return specific data
    with patch("custom_plugins.context_injection_plugin.get_agent_snapshot") as mock_get_snapshot:
        def side_effect(session, agent_name):
            if agent_name == "IncidentDetectionAgent":
                return {
                    "service_name": "test-service",
                    "severity": "High",
                    "incident_summary": "Test incident",
                    "root_cause": "Test root cause",
                    "evidence": "Log error: 500 Internal Server Error"
                }
            elif agent_name == "SolutionGeneratorAgent":
                return {
                    "proposed_solution": "Fix the bug",
                    "mitigation_suggestions": "Restart service",
                    "patch": {
                        "files_to_modify": [{"path": "server.js"}],
                        "test_cases": ["Run unit tests"]
                    }
                }
            elif agent_name == "PRCreatorAgent":
                return {
                    "pr_url": "http://github.com/pr/1",
                    "pr_number": "1",
                    "merged": False
                }
            return {}
            
        mock_get_snapshot.side_effect = side_effect
        
        await plugin.before_agent_callback(agent=agent, callback_context=callback_context)
    
    # Verify injection
    injected_text = callback_context.input.parts[0].text
    print(injected_text)
    
    assert "INCIDENT DETECTION:" in injected_text
    assert "- Evidence: Log error: 500 Internal Server Error" in injected_text
    assert "SOLUTION GENERATION:" in injected_text
    assert "- Technical Details: [{'path': 'server.js'}]" in injected_text
    assert "- Verification Steps: ['Run unit tests']" in injected_text
    assert "PR CREATION:" in injected_text
    assert "- PR Status: Open" in injected_text
