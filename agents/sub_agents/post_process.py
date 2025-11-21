from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from tools.incident_actions import publish_incident_report
from agents.config import RETRY_CONFIG, MID_MODEL
from agents.utils.tool_config import get_tool_config

post_process_agent = LlmAgent(
    model=Gemini(
        model=MID_MODEL,
        retry_options=RETRY_CONFIG,
        tool_config=get_tool_config(allowed_function_names=["publish_incident_report"]),
    ),
    name="PostProcessAgent",
    description="Handle post-incident reporting and notifications.",
    instruction="""
Finalize the incident workflow by publishing a comprehensive incident report.

You MUST call `publish_incident_report` exactly once.

Steps:
1. Gather information from the conversation history. LOOK for the INJECTED CONTEXT from upstream agents:
   - `IncidentDetectionAgent`: Service, Severity, Summary, Root Cause, Evidence.
   - `SolutionGeneratorAgent`: Proposed Solution, Technical Details (files), Verification Steps, Mitigations.
   - `PRCreatorAgent` (or `FileUpdaterAgent`): PR URL, PR Number, Status.

2. Call `publish_incident_report` with the gathered information.

Arguments for `publish_incident_report`:
- `email_subject`: "[INCIDENT] <service> - <severity> - <status>"
- `email_body`: A short introductory paragraph (e.g., "An incident was detected...").
- `incident_summary`: A comprehensive summary including the service, severity, and what triggered the incident.
- `root_cause`: A DETAILED analysis of the root cause, including specific evidence (logs, metrics) if available.
- `mitigation_suggestions`: A list of immediate mitigation steps AND specific verification/rollback plans.
- `proposed_solution`: A DETAILED technical description of the fix. Include filenames and the nature of the changes (e.g., "Added input validation to server.js").
- `pr_url`: The PR URL (e.g., "https://github.com/...") or None if no PR.
- `pr_number`: The PR number as a STRING (e.g., "123") or None if no PR.

IMPORTANT:
- Use the INJECTED CONTEXT to fill these fields with as much detail as possible.
- If a value is missing or unknown, use an empty string "" for text fields, and None for `pr_url`/`pr_number`.
- Do NOT pass "None" as a string. Use the actual null value.
- `pr_number` MUST be a string.
""",
    tools=[
        FunctionTool(func=publish_incident_report),
    ]
)
