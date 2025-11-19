import pytest
from unittest.mock import MagicMock, patch
from google.genai import types
from google.adk.agents import InvocationContext
from agents.sub_agents.context_injector import IncidentContextInjector

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.state = {}
    return session

@pytest.fixture
def mock_message():
    return types.Content(parts=[types.Part(text="Original user message")])

@pytest.mark.asyncio
async def test_context_injection(mock_session, mock_message):
    # Mock get_agent_snapshot to return specific data
    with patch("agents.sub_agents.context_injector.get_agent_snapshot") as mock_get_snapshot:
        def side_effect(session, agent_name):
            if agent_name == "IncidentDetectionAgent":
                return {
                    "service_name": "TestService",
                    "severity": "High",
                    "incident_summary": "Test Summary",
                    "root_cause": "Test Root Cause"
                }
            elif agent_name == "SolutionGeneratorAgent":
                return {
                    "proposed_solution": "Test Solution",
                    "mitigation_suggestions": "Test Mitigation"
                }
            elif agent_name == "PRCreatorAgent":
                return {
                    "pr_url": "http://github.com/test/pr/1",
                    "pr_number": "1"
                }
            return {}
        
        mock_get_snapshot.side_effect = side_effect

        # Create agent and context
        agent = IncidentContextInjector()
        mock_ctx = MagicMock(spec=InvocationContext)
        mock_ctx.session = mock_session
        mock_ctx.input = mock_message

        # Run agent
        gen = agent._run_async_impl(mock_ctx)
        async for _ in gen:
            pass
        
        # Verify get_agent_snapshot was called for all agents
        assert mock_get_snapshot.call_count >= 3
        
        # Verify the message has the injected context
        assert len(mock_message.parts) == 2
        context_text = mock_message.parts[0].text
        
        assert "--- CONTEXT FROM UPSTREAM AGENTS ---" in context_text
        assert "TestService" in context_text
        assert "Test Solution" in context_text
        assert "http://github.com/test/pr/1" in context_text
        assert "Original user message" in mock_message.parts[1].text
