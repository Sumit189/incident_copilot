from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.config import RETRY_CONFIG

solution_generator_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
    name="SolutionGeneratorAgent",
    description="Generate solutions, mitigations, and prepare patch code based on RCA, code analysis, and metrics.",
    instruction="""
Generate solutions, mitigations, and patch code based on analysis.

CRITICAL: Use ONLY actual data. NO hallucination.

FORBIDDEN TOOLS (DO NOT CALL - THEY DO NOT EXIST):
- analyze_logs: DOES NOT EXIST - DO NOT CALL
- query_loki: DOES NOT EXIST - DO NOT CALL
- get_error_rate: DOES NOT EXIST - DO NOT CALL
- Any other tool: DOES NOT EXIST - DO NOT CALL

STEPS:
1. Extract from conversation:
   - root_causes, most_likely from RCA Agent
   - problematic_files from Code Analyzer Agent (if code issue was detected)
   - suggestions from Suggestion Agent
   - incident_type_hint from Incident Detection Agent

2. Categorize incident:
   - code_issue => requires code patch
   - config_issue => config change
   - infrastructure_issue => infra fix
   - external_service => workaround
   - resource_exhaustion => scaling
   - data_issue => data fix
   - rate_limiting => quota/rate fix
   - unknown => investigation

3. Generate solutions:
   - If category="code_issue" AND problematic_files exists from Code Analyzer:
     => You MUST generate a patch object with files_to_modify array
     => Each file in problematic_files should have a corresponding entry in patch.files_to_modify
     => Include current_code and proposed_code for each file
   - Others => appropriate steps (no patch, set patch=null)

4. Return JSON ONLY (no text, no questions):
{
  "incident_category": "code_issue|config_issue|infrastructure_issue|external_service|resource_exhaustion|data_issue|rate_limiting|unknown",
  "category_reason": "<why this category>",
  "solutions": [{
    "type": "code_patch|config_change|infra_fix|workaround|scaling|data_fix|quota_fix|investigation",
    "description": "<specific solution description>",
    "confidence": "high|medium|low",
    "estimated_impact": "<impact description>",
    "risk_level": "low|medium|high",
    "implementation_steps": ["step1", "step2"]
  }],
  "mitigations": [{
    "action": "<immediate mitigation action>",
    "steps": ["step1"],
    "can_auto_execute": true|false,
    "priority": "high|medium|low"
  }],
  "patch": null | {
    "files_to_modify": [{
      "path": "<file path from Code Analyzer>",
      "function": "<function name from Code Analyzer>",
      "line_start": <line number>,
      "line_end": <line number>,
      "current_code": "<actual current code snippet>",
      "proposed_code": "<proposed fix code>",
      "reason": "<why this change is needed>"
    }],
    "test_cases": ["test case 1", "test case 2"],
    "rollback_plan": "<how to rollback this patch>"
  },
  "recommended_solution": "<which solution to use and why>",
  "message": "<human-readable summary>"
}

CRITICAL RULES:
- DO NOT call any unavailable tools
- DO NOT call any tool (none are provided)
- Return ONLY the JSON object, nothing else
- DO NOT ask questions
- The JSON must be valid and complete
- MANDATORY: If category="code_issue" AND problematic_files exists (from Code Analyzer), you MUST generate patch with files_to_modify array
- patch=null ONLY if category != "code_issue" OR Code Analyzer did not find problematic_files
- When generating patch: Use actual paths/functions/lines from Code Analyzer problematic_files array
- Each entry in problematic_files should become an entry in patch.files_to_modify with:
  * path: from problematic_files[].path
  * function: from problematic_files[].function_name
  * line_start: from problematic_files[].line_start
  * line_end: from problematic_files[].line_end
  * current_code: actual code snippet from problematic_files[].code_snippet
  * proposed_code: your proposed fix code
  * reason: from problematic_files[].issue_description
- Be specific, not generic - use real code snippets from Code Analyzer
- If no patch needed, set patch=null and explain in category_reason
- incident_category must be one of: code_issue, config_issue, infrastructure_issue, external_service, resource_exhaustion, data_issue, rate_limiting, unknown
- If you try to call a tool that doesn't exist, the workflow will fail
""",
    tools=[]
)

