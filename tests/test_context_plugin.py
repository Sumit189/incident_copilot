import pytest
from unittest.mock import MagicMock, patch
from google.genai import types
from custom_plugins.context_injection_plugin import ContextInjectionPlugin

@pytest.mark.asyncio
async def test_plugin_injection():
    # Mock session and context
    mock_session = MagicMock()
    mock_message = types.Content(parts=[types.Part(text="Original user message")])
    
    mock_callback_context = MagicMock()
    mock_callback_context.session = mock_session
    mock_callback_context.input = mock_message
    
    mock_agent = MagicMock()
    mock_agent.name = "PostProcessAgent"
    
    plugin = ContextInjectionPlugin()
    
    # Mock get_agent_snapshot
    with patch("custom_plugins.context_injection_plugin.get_agent_snapshot") as mock_get_snapshot:
        def side_effect(session, agent_name):
            if agent_name == "IncidentDetectionAgent":
                return {
                    "service_name": "TestService",
                    "severity": "High",
                    "incident_summary": "Test Summary",
                    "root_cause": "Test Root Cause"
                }
            return {}
        mock_get_snapshot.side_effect = side_effect
        
        # Run callback
        await plugin.before_agent_callback(agent=mock_agent, callback_context=mock_callback_context)
        
        # Verify injection
        assert len(mock_message.parts) == 2
        context_text = mock_message.parts[0].text
        assert "--- CONTEXT FROM UPSTREAM AGENTS ---" in context_text
        assert "TestService" in context_text
        assert "Original user message" in mock_message.parts[1].text

@pytest.mark.asyncio
async def test_plugin_skip_other_agents():
    mock_agent = MagicMock()
    mock_agent.name = "OtherAgent"
    
    plugin = ContextInjectionPlugin()
    
    # Should return immediately
    await plugin.before_agent_callback(agent=mock_agent, callback_context=MagicMock())
