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

CRITICAL: Use ONLY actual data provided. NO hallucination.

STEPS:
1. Extract from Incident Detection Agent output (provided in input or conversation history):
   - Look for JSON data starting with "Incident Detection Agent Output:" or similar
   - Extract: affected_services, error_summary, initial_symptoms, incident_type_hint, log_query_used
   - affected_services: List of affected services
   - error_summary: Contains total_errors, total_warnings, error_types, warning_types
   - initial_symptoms: Array of symptoms from logs
   - incident_type_hint: Type of incident (code_issue, config_issue, infrastructure_issue, etc.)
   - log_query_used: The actual log query that was used

2. Analyze actual error patterns from error_summary (Chain of Thought):
   - Review `error_types` and `initial_symptoms` carefully.
   - Match against known patterns and use specific terminology:
     * Database connection timeouts => "connection pool", "pool exhaustion", "connection pool starvation"
     * Memory errors (OutOfMemoryError, heap) => "memory leak", "heap", "cache" (often involved in memory leaks), "not released" (resources not freed), "resource leak"
     * Network timeouts to external services => "external api", "external service", "network", "connectivity", "timeout"
     * Authentication failures with spikes/patterns => "authentication", "credentials", "config" (often misconfiguration), "token" (if token-based auth), "auth"
   - **Memory leak analysis**: If OutOfMemoryError or heap errors are present, mention "cache" (cache management often causes leaks) and "not released" (memory not being freed properly).
   - **Authentication failure analysis**: If authentication failures show spikes/patterns, mention "config" (misconfiguration is common) and "token" (if applicable to the auth mechanism).
     * 429 errors => API quota/rate limiting
     * Memory/CPU errors => Resource exhaustion
     * Database errors => Connection issues
     * Config errors => Configuration problems
     * External service errors => Dependency failures
     * Application errors => Code bugs
     * Warning logs => Config/infrastructure issues
   - Formulate a hypothesis based on the strongest evidence.
   - Use the specific terminology above when describing root causes to ensure clarity.

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

- All data comes from Incident Detection Agent output (provided in input or conversation history).
- Extract data ONLY from Incident Detection Agent JSON output provided to you.
- Parse the JSON from the input text if it's provided directly (look for JSON after "Incident Detection Agent Output:").
- Use error_summary.error_types, error_summary.warning_types, and initial_symptoms for evidence.
- Return ONLY the JSON object, nothing else.
- DO NOT ask questions or request more information - use what is provided.
""",
    tools=[]
)

