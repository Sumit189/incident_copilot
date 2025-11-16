from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.github import create_or_update_file
from incident_copilot.config import RETRY_CONFIG
from incident_copilot.tools import check_pr_workflow_gate


def _create_file_updater_agent():
    tools_list = [
        FunctionTool(func=check_pr_workflow_gate),
        FunctionTool(func=create_or_update_file),
    ]

    return LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="FileUpdaterAgent",
        description="Commit the generated patch to the incident branch via GitHub REST API.",
        instruction="""
Update all files in the patch.

AVAILABLE TOOLS:
- check_pr_workflow_gate: Returns whether PR workflow is currently allowed.
- create_or_update_file: Create or update a repository file on the specified branch (handles encoding + commits).

STEPS:
0. Call check_pr_workflow_gate(). If allowed=false => return {"status": "skipped", "message": reason or "PR workflow blocked", "files_updated": 0}.
1. Extract from conversation history (MANDATORY):
   - Branch Creator Agent output => branch_name (must be non-null)
   - Solution Generator Agent output => patch.files_to_modify array
   - If branch_name missing OR files_to_modify empty => return {"status": "skipped", "message": "No files to update or branch not created"}

2. Update EVERY file in patch.files_to_modify:
   - For each entry:
     * path = file_entry.path
     * proposed_code = file_entry.proposed_code
     * reason = file_entry.reason (use for commit message)
     * Call create_or_update_file(path="<path>", content="<proposed_code>", branch="<branch_name>", message="Fix: <reason>")
   - DO NOT skip files. Stop immediately if the helper returns status="error" and surface that message.

3. Return JSON:
{
  "status": "success|error|skipped",
  "files_updated": <number>,
  "branch_name": "<branch_name>",
  "message": "<status>"
}

CRITICAL RULES:
- You MUST call create_or_update_file for EVERY file in patch.files_to_modify
- Always use the exact branch_name returned by BranchCreatorAgent (including suffix if added)
- If repository configuration is missing, return status="skipped"
- Surface helper error messages directly so operators know what failed
""",
        tools=tools_list
    )


file_updater_agent = _create_file_updater_agent()

