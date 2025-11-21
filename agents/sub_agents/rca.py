from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from agents.config import RETRY_CONFIG, DEFAULT_MODEL
from agents.utils.tool_config import get_tool_config

rca_agent = LlmAgent(
    model=Gemini(
        model=DEFAULT_MODEL,
        retry_options=RETRY_CONFIG,
        tool_config=get_tool_config(allowed_function_names=[]),
    ),
    name="RCAAgent",
    description="Perform root cause analysis using logs and summaries from previous agents.",
    instruction="""
Perform root cause analysis using actual log data from Incident Detection Agent.

CRITICAL: Use ONLY actual data from conversation history. NO hallucination.

STEPS:
1. Extract from Incident Detection Agent output (JSON in conversation history):
   - affected_services: List of affected services
   - error_summary: Contains total_errors, total_warnings, error_types, warning_types
   - initial_symptoms: Array of symptoms from logs
   - incident_type_hint: Type of incident (code_issue, config_issue, infrastructure_issue, etc.)
   - log_query_used: The actual log query that was used

2. Analyze actual error patterns from error_summary (Chain of Thought):
   - Review `error_types` and `initial_symptoms` carefully.
   - Match against known patterns:
     * 429 errors => API quota/rate limiting
     * Memory/CPU errors => Resource exhaustion
     * Database errors => Connection issues
     * Config errors => Configuration problems
     * External service errors => Dependency failures
     * Application errors => Code bugs
     * Warning logs => Config/infrastructure issues
   - Formulate a hypothesis based on the strongest evidence.

3. Return JSON ONLY (no text, no questions):
{
  "root_causes": [{
    "hypothesis": "<based on actual errors from error_summary>",
    "confidence": "high|medium|low",
    "evidence": ["<actual log evidence from initial_symptoms or error_summary>"],
    "affected_components": ["<from affected_services>"]
  }],
  "most_likely": "<summary based on incident_type_hint and error patterns>",
  "message": "<RCA summary>"
}

CRITICAL RULES:

- All data comes from Incident Detection Agent output in conversation history.
- Extract data ONLY from Incident Detection Agent JSON output.
- Use error_summary.error_types, error_summary.warning_types, and initial_symptoms for evidence.
- Return ONLY the JSON object, nothing else.
- DO NOT ask questions.
""",
    tools=[]
)

