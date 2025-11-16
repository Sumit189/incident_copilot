"""
Conditional Solution and PR workflow - only runs if incident is a code issue.
"""

import json
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.config import RETRY_CONFIG
from incident_copilot.sub_agents.solution_generator import solution_generator_agent
from incident_copilot.sub_agents.pr_executor import pr_executor_agent
from incident_copilot.tools import block_pr_workflow


def create_conditional_solution_pr_workflow():
    """
    Create a conditional solution and PR workflow that only runs if the incident is a 'code_issue'.
    """
    solution_pr_guard_agent = LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="SolutionPRGuardAgent",
        description="Check if the incident is a 'code_issue' and conditionally run Solution Generator and PR Executor.",
        instruction="""
Check the incident_type_hint from the IncidentDetectionAgent's output.

STEPS:
1. Find IncidentDetectionAgent's JSON output in conversation history:
   - Look for JSON with "incident_type_hint" field.
   - Extract incident_type_hint (e.g., "code_issue", "config_issue", "infrastructure_issue").

2. Decision logic:
   - If incident_type_hint is "code_issue":
     => Return: "PROCEED: Incident is a code issue. Running Solution Generator and PR Executor."
   - Else (not a code issue):
     => Return: "SKIP: Not a code issue. Skipping Solution Generator and PR Executor."

3. Response format (exactly one line):
   - "SKIP: Not a code issue. Skipping Solution Generator and PR Executor."
   - "PROCEED: Incident is a code issue. Running Solution Generator and PR Executor."

4. If you output SKIP, you MUST call block_pr_workflow(reason="<explain why>") so downstream agents know to stop PR work.

CRITICAL RULES:
- Only proceed if incident_type_hint is "code_issue".
- If skipping, return a clear "SKIP" message.
- Do NOT call stop_workflow here; this guard only controls the Solution/PR sub-workflow.
""",
        tools=[FunctionTool(func=block_pr_workflow)]
    )

    pr_patch_guard_agent = LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="PRPatchGuardAgent",
        description="Ensure PR executor only runs when Solution Generator produced concrete code changes.",
        instruction="""
Inspect the latest SolutionGeneratorAgent JSON output before allowing PR execution.

STEPS:
1. Locate the SolutionGeneratorAgent JSON response in the transcript.
2. Extract the "patch" object. Determine if:
   - patch is null, OR
   - patch.files_to_modify is missing/empty, OR
   - Every entry lacks proposed_code/current_code (no actionable diff).
   => If any of the above are true, respond: "SKIP: No patch to apply. Skipping PR executor."
3. If at least one file entry exists with proposed_code content, respond:
   "PROCEED: Patch ready. Running PR executor."

RULES:
- This guard prevents unnecessary branch/PR work when no code update exists.
- Do NOT allow PR executor to run unless there is at least one concrete file change.
- If you respond with SKIP, immediately call block_pr_workflow(reason="<why>") so downstream agents skip deterministically.
- Responses must be exactly one sentence starting with SKIP or PROCEED as shown above.
""",
        tools=[FunctionTool(func=block_pr_workflow)]
    )

    solution_and_pr_workflow = SequentialAgent(
        name="SolutionAndPRWorkflow",
        sub_agents=[solution_generator_agent, pr_patch_guard_agent, pr_executor_agent]
    )

    conditional_solution_pr_workflow = SequentialAgent(
        name="ConditionalSolutionPRWorkflow",
        sub_agents=[solution_pr_guard_agent, solution_and_pr_workflow]
    )

    return conditional_solution_pr_workflow

