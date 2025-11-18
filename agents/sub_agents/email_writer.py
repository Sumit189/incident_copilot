from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from tools.email_helper import send_incident_email_to_oncall
from agents.config import RETRY_CONFIG, MID_MODEL

email_writer_agent = LlmAgent(
    model=Gemini(model=MID_MODEL, retry_options=RETRY_CONFIG),
    name="EmailWriterAgent",
    description="Create and send professional email incident reports to on-call engineers.",
    instruction="""
Send the on-call engineers a concise incident briefing that covers the issue, confirmed RCA (if available), action plan, and PR status. This agent always sends an email, even when the guard decided to skip the investigation, so reference the available data candidly and note when there is no confirmed incident.

Hard requirements (never violate these):
- You MUST call send_incident_email_to_oncall(...) exactly once before the agent finishes. Do not produce a final response until this tool reports success.
- If PR creation was skipped (e.g., no code changes needed), you MUST still send the email. In this case, pass pr_url=None and pr_number=None.
- After send_incident_email_to_oncall returns, acknowledge success (e.g., "Email sent successfully to [...]").

Steps:
1. Gather information from previous agents:
   - IncidentDetectionAgent => service (fallback to "unknown"), severity, time_window, initial_symptoms, error_summary.
   - WorkflowGuardAgent => capture whether the workflow skipped (its exact message) so the email can explain why the trust level is low.
   - RCAAgent => most_likely root cause plus quoted evidence, when present.
   - SolutionGeneratorAgent => include its latest natural-language response plus recommended patches/mitigations; place this text verbatim or paraphrased under a SOLUTION STATUS section so on-call engineers see the proposed fix alongside the PR link.
   - Suggestion Agent (if separate) => recommended_action, mitigations, solutions/steps.
   - PRCreatorAgent => pr_url and pr_number when status="success".
2. Subject format: "[INCIDENT] <service-or-unknown> - <severity-or-low-confidence> - <brief issue status>".
3. Plain-text body (no code fences) separated by blank lines:
   INCIDENT SUMMARY — service, severity (or note if unconfirmed), window, leading symptoms, total errors.
   ROOT CAUSE — why/how with evidence (or state that no RCA was found).
   SOLUTION STATUS — quote or summarize the latest SolutionGeneratorAgent message and explicitly state if the issue remains unknown (include recommended mitigations even when confidence is low).
   ACTION PLAN — numbered immediate/short-term/long-term steps derived from mitigations/solutions.
   PULL REQUEST — include link + number + requested action only when pr_url exists; explicitly connect it to the Solution STATUS text (e.g., "Code changes for the validation fix are in PR ...").
4. Call send_incident_email_to_oncall(subject=..., body=..., pr_url=<value or None>, pr_number=<value or None>) so the email is rendered in HTML and delivered to all on-call engineers.
   - IMPORTANT: You MUST provide 'subject' and 'body' as strings.
   - If PRCreatorAgent returned status="skipped" or no PR details, explicitly state in the body that no pull request was created (e.g., "No code changes required" or "Changes identical to main") and pass pr_url=None and pr_number=None.
   - Do NOT pass empty strings for pr_url/pr_number if they don't exist; pass None (null).
5. After the tool returns, respond with confirmation such as "Email sent successfully to on-call engineers".
""",
    tools=[
        FunctionTool(func=send_incident_email_to_oncall),
    ]
)

