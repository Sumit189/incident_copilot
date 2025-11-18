from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from agents.github import create_incident_branch, verify_patch
from agents.config import RETRY_CONFIG, DEFAULT_MODEL


def _create_branch_creator_agent():


    return LlmAgent(
        model=Gemini(model=DEFAULT_MODEL, retry_options=RETRY_CONFIG),
        name="BranchCreatorAgent",
        description="Create a new branch for the PR.",
        instruction="""
Create a new branch for the PR whenever Solution Generator indicates a code issue.

AVAILABLE TOOLS:
- create_incident_branch: Creates a GitHub branch from the configured repository/base branch. Automatically appends a suffix if the reference already exists and returns the final branch name.
- verify_patch: Checks if the proposed file changes are actually different from the base branch.

STEPS:
1. Extract from conversation history:
   - incident_category, patch from Solution Generator Agent output (JSON)
   - If category != "code_issue" OR patch is null OR patch.files_to_modify is missing/empty => return {"status": "skipped", "branch_name": null, "message": "No branch needed"}
   - affected_services from Incident Detection Agent output (JSON)
   - service: Use first service from affected_services OR use "unknown-service"
   - incident_id: Generate "incident-<service>-<timestamp>" (replace with actual values)

2. Verify patch necessity:
   - Call verify_patch(files=patch.files_to_modify)
   - If verify_patch returns needs_changes=false => return {"status": "skipped", "branch_name": null, "message": "Patch is identical to main branch; skipping."}

3. Generate branch name:
   - Format: "fix/incident-<incident_id>-<timestamp>"
   - Example: "fix/incident-issue-tester-1700226960"
   - If create_incident_branch reports a duplicate, it appends a short suffix automatically. ALWAYS use the branch_name returned by the tool in later steps.

4. Create branch:
   - MANDATORY: Call create_incident_branch(branch_name="<generated_branch_name>")
   - Only override base_branch if you explicitly need a different base than the configured default.

5. Return JSON:
{
  "status": "success|error|skipped",
  "branch_name": "<branch_name>" | null,
  "message": "<status message>"
}

CRITICAL RULES:
- Only create branch if category="code_issue", patch != null, patch.files_to_modify has entries, AND repository is configured
- ALWAYS call verify_patch before creating a branch. If it says no changes needed, SKIP branch creation.
- Generate unique branch name with incident_id and timestamp; the helper handles duplicates automatically
- Return the final branch_name so File Updater Agent can use it
- If repository not configured, return status="skipped"
""",
        tools=[
            FunctionTool(func=create_incident_branch),
            FunctionTool(func=verify_patch),
        ]
    )


branch_creator_agent = _create_branch_creator_agent()

