from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from agents.config import RETRY_CONFIG, DEFAULT_MODEL
from agents.utils.tool_config import get_tool_config

suggestion_agent = LlmAgent(
    model=Gemini(
        model=DEFAULT_MODEL,
        retry_options=RETRY_CONFIG,
        tool_config=get_tool_config(allowed_function_names=[]),
    ),
    name="SuggestionAgent",
    description="Generate actionable remediation steps and fix suggestions based on RCA.",
    instruction="""
Generate actionable remediation steps based on RCA.

CRITICAL: Use ONLY actual data. NO hallucination.


STEPS:
1. Extract from conversation:
   - service from Incident Detection Agent (affected_services)
   - root_causes, most_likely from RCA Agent
   - error_summary from Incident Detection Agent (error_types, warning_types)

2. Generate fixes based on actual errors:
   - 429/quota errors => API quota/rate limiting fixes
   - Config errors => Configuration changes
   - App bugs => Code patches
   - Resource exhaustion => Scaling
   - API issues => API mitigations

3. Return JSON:
{
  "suggestions": [{
    "type": "config|patch|scale|rollback|api",
    "description": "<specific action>",
    "steps": ["step1", "step2"],
    "priority": "high|medium|low",
    "estimated_impact": "<impact>"
  }],
  "recommended_action": "<summary>",
  "message": "<summary>"
}

RULES:
- Be SPECIFIC: "Request quota increase from GCP Console" not "check logs"
- Be ACTIONABLE: Provide executable steps (e.g., "Run `kubectl scale deployment...`" or "Update env var `MAX_RETRIES` to 5")
- Base on ACTUAL errors, not generic suggestions

CRITICAL RULES:
- DO NOT call any tools (none are provided).
- All data comes from conversation history.
- If you try to call a tool that doesn't exist, the workflow will fail.
""",
    tools=[]
)

