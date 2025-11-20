from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from agents.github import create_pull_request
from agents.config import RETRY_CONFIG


def _create_pr_creator_agent():
    tools_list = [
        FunctionTool(func=create_pull_request),
    ]

    return LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="PRCreatorAgent",
        description="Open (or reuse) the pull request for the incident fix via GitHub REST API.",
        instruction="""
Create the pull request once the branch and file updates are ready.

AVAILABLE TOOLS:
- create_pull_request: Opens a pull request (and returns an existing one if GitHub reports it already exists).

STEPS:
1. Extract from conversation history:
   - patch, recommended_solution, mitigations from Solution Generator Agent output (JSON)
   - root_cause, most_likely from RCA Agent output (JSON)
   - affected_services from Incident Detection Agent output (JSON)
   - branch_name from File Updater Agent output (must be non-null)
   - files_updated from File Updater Agent output (must be > 0 to proceed)
   - service: Use first service from affected_services OR "unknown-service"
   - incident_id: Generate "incident-<service>-<timestamp>" for contextual references
   - If branch_name is null OR files_updated == 0 => return {"status": "skipped", "pr_url": null, "pr_number": null, "message": "Branch or files not ready"}

2. Build PR content:
   - Title: "[AUTO-FIX] <service>: <root_cause_summary>"
   - Body must include:
     * Incident summary (service, severity, time window)
     * Root cause and evidence (from RCA output)
     * Proposed fix details and code summary (from Solution Generator output)
     * Mitigations / rollback / validation steps
     * Checklist for reviewers

3. Create PR:
   - MANDATORY: Call create_pull_request(title="<pr_title>", head="<branch_name>", base="<default or override>", body="<pr_description>")
   - The helper returns status "success" for a new PR or "exists" if GitHub already has one; both are acceptable and must be surfaced.
   - Capture pr_number, pr_url, branch, merged flag, and helper message.

4. Return JSON:
{
  "status": "success|exists|error|skipped",
  "pr_number": <number> | null,
  "pr_url": "<url>" | null,
  "branch": "<branch_name>",
  "merged": false,
  "incident_category": "<category>",
  "message": "<status message>"
}

CRITICAL RULES:
- You MUST call create_pull_request after branch and files are ready (unless skipping for missing data)
- Use the branch_name exactly as provided by FileUpdaterAgent
- DO NOT attempt to modify files. File updates are handled by FileUpdaterAgent. Your ONLY job is to create the PR.
- Include pr_url and pr_number so PostProcessAgent can reference them
- If the helper returns status="error", propagate its message verbatim
""",
        tools=tools_list
    )


pr_creator_agent = _create_pr_creator_agent()
