from google.adk.plugins import BasePlugin
from google.genai import types
from agents.utils.state import get_agent_snapshot
import logging

class ContextInjectionPlugin(BasePlugin):
    """
    Injects context from upstream agents into the PostProcessAgent's input.
    """

    def __init__(self):
        super().__init__("context_injection")

    async def before_agent_callback(self, *, agent, callback_context):
        if agent.name != "PostProcessAgent":
            return

        session = getattr(callback_context, "session", None)
        if not session:
            return

        # 1. Fetch context from upstream agents
        incident_data = get_agent_snapshot(session, "IncidentDetectionAgent") or {}
        solution_data = get_agent_snapshot(session, "SolutionGeneratorAgent") or {}
        pr_data = get_agent_snapshot(session, "PRCreatorAgent") or {}

        # 2. Construct Context Summary
        context_summary = "--- CONTEXT FROM UPSTREAM AGENTS ---\n"

        if incident_data:
            context_summary += f"INCIDENT DETECTION:\n"
            context_summary += f"- Service: {incident_data.get('service_name', 'Unknown')}\n"
            context_summary += f"- Severity: {incident_data.get('severity', 'Unknown')}\n"
            context_summary += f"- Summary: {incident_data.get('incident_summary', 'Unknown')}\n"
            context_summary += f"- Root Cause: {incident_data.get('root_cause', 'Unknown')}\n"
            context_summary += f"- Evidence: {incident_data.get('evidence', 'None provided')}\n\n"

        if solution_data:
            context_summary += f"SOLUTION GENERATION:\n"
            context_summary += f"- Proposed Solution: {solution_data.get('proposed_solution', 'Unknown')}\n"
            context_summary += f"- Technical Details: {solution_data.get('patch', {}).get('files_to_modify', 'See PR for details')}\n"
            context_summary += f"- Verification Steps: {solution_data.get('patch', {}).get('test_cases', 'None provided')}\n"
            context_summary += f"- Mitigation: {solution_data.get('mitigation_suggestions', 'Unknown')}\n\n"

        if pr_data:
            context_summary += f"PR CREATION:\n"
            context_summary += f"- PR URL: {pr_data.get('pr_url', 'None')}\n"
            context_summary += f"- PR Number: {pr_data.get('pr_number', 'None')}\n"
            context_summary += f"- PR Status: {'Merged' if pr_data.get('merged') else 'Open'}\n\n"

        context_summary += "--- END CONTEXT ---\n\n"
        context_summary += "Use the above context to populate the incident report."

        # 3. Inject into message
        # callback_context.input is the message being passed to the agent
        user_message = getattr(callback_context, "input", None)
        if user_message and isinstance(user_message, types.Content) and user_message.parts:
            context_part = types.Part(text=context_summary)
            user_message.parts.insert(0, context_part)
