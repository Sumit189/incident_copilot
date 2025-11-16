from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.config import RETRY_CONFIG

suggestion_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
    name="SuggestionAgent",
    description="Generate actionable remediation steps and fix suggestions based on RCA.",
    instruction="""
Generate actionable remediation steps based on RCA.

CRITICAL: Use ONLY actual data. NO hallucination.

FORBIDDEN TOOLS (DO NOT CALL - THEY DO NOT EXIST):
- analyze_logs: DOES NOT EXIST - DO NOT CALL
- query_loki: DOES NOT EXIST - DO NOT CALL
- get_error_rate: DOES NOT EXIST - DO NOT CALL
- Any other tool: DOES NOT EXIST - DO NOT CALL

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
- Be ACTIONABLE: Provide executable steps
- Base on ACTUAL errors, not generic suggestions

CRITICAL RULES:
- DO NOT call analyze_logs - THIS TOOL DOES NOT EXIST
- DO NOT call query_loki - THIS TOOL DOES NOT EXIST
- DO NOT call get_error_rate - THIS TOOL DOES NOT EXIST
- DO NOT call any tool that is not explicitly listed (there are none)
- All data comes from conversation history (Incident Detection Agent, RCA Agent outputs)
- If you try to call a tool that doesn't exist, the workflow will fail
""",
    tools=[]
)

