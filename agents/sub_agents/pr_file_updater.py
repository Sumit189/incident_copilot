from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from agents.github import create_or_update_file, apply_change_to_file, read_file_content, create_incident_branch
from agents.config import RETRY_CONFIG
    
    
def _create_file_updater_agent():


    return LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="FileUpdaterAgent",
        description="Create the incident branch and commit the generated patch via GitHub REST API.",
        instruction="""
Create a new branch and update files in the patch using targeted search-and-replace.

AVAILABLE TOOLS:
- create_incident_branch: Creates a GitHub branch. Automatically appends a suffix if needed.
- apply_change_to_file: Preferred. Replaces 'search_content' with 'replace_content'. Supports flexible whitespace matching.
- read_file_content: Read the actual file content from the branch. Use this if apply_change_to_file fails.
- create_or_update_file: Fallback. Overwrites the ENTIRE file. Use ONLY if you have the FULL file content.

STEPS:
1. Extract from conversation history (MANDATORY):
   - Solution Generator Agent output => patch.files_to_modify array
   - affected_services from Incident Detection Agent output (JSON)
   - service: Use first service from affected_services OR "unknown-service"
   - incident_id: Generate "incident-<service>-<timestamp>" (replace with actual values)
   - If files_to_modify is empty => return {"status": "skipped", "message": "No files to update"}

2. Create Branch:
   - Generate branch name: "fix/incident-<incident_id>-<timestamp>" (e.g., "fix/incident-issue-tester-1700226960")
   - Call create_incident_branch(branch_name="<generated_name>")
   - CHECK RESULT: If status="error", STOP and return the error.
   - Capture the FINAL branch_name returned by the tool (it might have a suffix).

3. Update EVERY file in patch.files_to_modify:
   - Use the branch_name from Step 2.
   - For each entry:
     * path = file_entry.path
     * original = file_entry.original_code_snippet (or current_code)
     * new_code = file_entry.new_code_snippet (or proposed_code)
     * reason = file_entry.reason
     
     * STRATEGY:
       - Attempt 1: Call apply_change_to_file(path, original, new_code, branch_name)
       - If apply_change_to_file returns status="error" and message contains "Search content not found":
         * Attempt 2 (Recovery):
           1. Call read_file_content(path, branch_name) to get the ACTUAL content.
           2. If read_file_content returns "Error:...", stop and report error.
           3. Locate the code block in the actual content that corresponds to 'original' (it might differ slightly).
           4. Construct the FULL new file content by replacing the found block with 'new_code'.
           5. Call create_or_update_file(path, FULL_CONTENT, branch_name, message="Fix: <reason> (Recovered)")
       
       - If only 'new_code' is present (no original) and it looks like a FULL file:
         Call create_or_update_file(path, new_code, branch_name)

   - DO NOT skip files. Stop immediately if the helper returns status="error" and surface that message.

4. Return JSON:
{
  "status": "success|error|skipped",
  "files_updated": <number>,
  "branch_name": "<branch_name>",
  "message": "<status>"
}

CRITICAL RULES:
- You MUST create the branch FIRST.
- You MUST call apply_change_to_file for targeted edits to preserve other code.
- If targeted edit fails, you MUST try to recover by reading the file and overwriting it with the correct content.
- If repository configuration is missing, return status="skipped".
- Surface helper error messages directly.
""",
        tools=[
            FunctionTool(func=create_incident_branch),
            FunctionTool(func=apply_change_to_file),
            FunctionTool(func=read_file_content),
            FunctionTool(func=create_or_update_file),
        ]
    )


file_updater_agent = _create_file_updater_agent()

