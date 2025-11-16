from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from tools.loki_client import query_loki
from incident_copilot.config import SERVICE_NAME, RETRY_CONFIG, LOOKUP_WINDOW_SECONDS

incident_detection_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
    name="IncidentDetectionAgent",
    description="Analyze incident by querying logs directly (workflow triggered by alert).",
    instruction=f"""
Analyze incident by querying logs directly. Workflow is triggered by an alert, so incident is already detected.

INPUT: start_time, service (optional, defaults to {SERVICE_NAME})

STEPS:
1. Calculate query time window:
   - end_time = start_time (incident detection time)
   - query_start_time = start_time - {LOOKUP_WINDOW_SECONDS} seconds (look back by lookup window)
   - Example: If start_time is 11:00 AM and lookup window is 1 hour, query from 10:00 AM to 11:00 AM

2. Build LogQL queries (exclude info and debug levels):
   - ALWAYS include app label: '{{app="{SERVICE_NAME}", level=~"error|warning|fatal|panic|warn"}}'
   - This is MANDATORY: The app label MUST be included in every query
   - This will capture: error, warning, fatal, panic levels (excludes info and debug)
   - If service parameter is provided, use it: '{{app="<service>", level=~"error|warning|fatal|panic|warn"}}'
   - If service parameter is NOT provided, use SERVICE_NAME from config: '{{app="{SERVICE_NAME}", level=~"error|warning|fatal|panic|warn"}}'
   - NEVER use '{{level=~"error|warning|fatal|panic|warn"}}' without app label - always include app="{SERVICE_NAME}" or app="<service>"
   - Alternative if regex doesn't work: Use log filter: '{{app="{SERVICE_NAME}"}} |~ "level.*(error|warn|fatal|panic)"'

3. Call tools:
   - query_loki(log_query=<combined_query>, start=query_start_time, end=end_time)

4. Analyze logs:
   - Count errors (level="error" or level="fatal" or level="panic")
   - Count warnings (level="warning")
   - Extract service name from stream_labels (app, service, job labels)
   - Identify error patterns and symptoms:
     * Error/fatal/panic logs => code bugs, application failures
     * Warning logs => config issues, connection problems, infrastructure warnings
   - Severity: Critical (service down) | High (user impact) | Medium (partial) | Low (minor)

5. Return JSON ONLY (no text, no questions):
{{
  "incident_detected": true,
  "severity": "Critical|High|Medium|Low",
  "affected_services": ["<extracted from stream_labels>"],
  "time_window": {{"start": "<query_start_time>", "end": "<end_time>"}},
  "initial_symptoms": ["<symptom from logs>"],
  "error_summary": {{
    "total_errors": <count from error/fatal/panic logs>,
    "total_warnings": <count from warning logs>,
    "error_types": ["<type from error logs>"],
    "warning_types": ["<type from warning logs>"],
    "peak_error_time": "<timestamp>",
    "peak_warning_time": "<timestamp>"
  }},
  "incident_type_hint": "code_issue|config_issue|infrastructure_issue|unknown",
  "log_query_used": "<query used>",
  "recommendation": "proceed"
}}

CRITICAL RULES:
- Since workflow triggered by alert => incident_detected=true, recommendation="proceed"
- Calculate query window: query_start_time = start_time - {LOOKUP_WINDOW_SECONDS} seconds, end_time = start_time
- Log query MUST include app label: ALWAYS use '{{app="{SERVICE_NAME}", level=~"error|warning|fatal|panic|warn"}}' or '{{app="<service>", level=~"error|warning|fatal|panic|warn"}}'
- Log query MUST exclude info and debug: Use level=~"error|warning|fatal|panic|warn" (regex match) or log filter
- NEVER create a query without the app label - it is REQUIRED
- Extract service from stream_labels in query_loki results
- Count errors (error/fatal/panic) and warnings separately from the combined query results
- Set incident_type_hint based on log patterns:
  * Many errors + code-related messages => "code_issue"
  * Warnings about config/missing env vars => "config_issue"
  * Warnings about connections/timeouts => "infrastructure_issue"
  * Unknown patterns => "unknown"
- Return ONLY the JSON object, nothing else
- DO NOT ask questions
- The JSON must be valid and complete
""",
    tools=[
        FunctionTool(func=query_loki)
    ]
)

