from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.tools import get_on_call_engineers
from tools.email_helper import send_incident_email
from incident_copilot.config import RETRY_CONFIG

email_writer_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
    name="EmailWriterAgent",
    description="Create and send professional email incident reports to on-call engineers.",
    instruction="""
Send the on-call engineers a concise incident briefing that covers the issue, confirmed RCA, action plan, and PR status.

Absolute pre-check:
- Inspect IncidentDetectionAgent and WorkflowGuardAgent outputs first.
- If incident_detected=false, recommendation="skip", or the guard already said "SKIP: No incident detected. Workflow terminated.", do NOT call any tools and simply respond with "SKIP: Incident not confirmed. Email suppressed."

Steps (only when the incident is confirmed):
1. Call get_on_call_engineers() and keep the returned list (always pass a list of recipients to the email tool).
2. Gather information from previous agents:
   - IncidentDetectionAgent => service (fallback to "unknown"), severity, time_window, initial_symptoms, error_summary.
   - RCAAgent => most_likely root cause plus quoted evidence.
   - SolutionGeneratorAgent => include its latest natural-language response (e.g., "Solution Agent response ...") plus recommended patches/mitigations. This text must appear verbatim or paraphrased under a SOLUTION STATUS section so on-call engineers see the proposed fix alongside the PR link.
   - Suggestion Agent (if separate) => recommended_action, mitigations, solutions/steps.
   - PRCreatorAgent => pr_url and pr_number when status="success".
3. Subject format: "[INCIDENT] <service-or-unknown> - <severity> - <brief issue>".
4. Plain-text body (no code fences) separated by blank lines:
   INCIDENT SUMMARY — service, severity, window, leading symptoms, total errors.
   ROOT CAUSE — why/how with evidence.
   SOLUTION STATUS — quote or summarize the latest SolutionGeneratorAgent message (e.g., "Solution Agent response..." instructions) and detail the patch adjustments it recommends.
   ACTION PLAN — numbered immediate/short-term/long-term steps derived from mitigations/solutions.
   PULL REQUEST — include link + number + requested action only when pr_url exists; explicitly connect it to the Solution STATUS text (e.g., "Code changes for the validation fix are in PR ...").
5. Call send_incident_email(to=recipients, subject=..., body=..., pr_url=<value or None>, pr_number=<value or None>) so the email is rendered in HTML.
6. Respond with confirmation such as "Email sent successfully to ['sre@example.com']".
""",
    tools=[
        FunctionTool(func=send_incident_email),
        FunctionTool(func=get_on_call_engineers),
    ]
)

