from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from tools.loki_client import query_loki
from agents.config import RETRY_CONFIG, LOOKUP_WINDOW_SECONDS, BEST_MODEL

incident_detection_agent = LlmAgent(
    model=Gemini(model=BEST_MODEL, retry_options=RETRY_CONFIG),
    name="IncidentDetectionAgent",
    description="Analyze incident by querying logs directly (workflow triggered by alert).",
    instruction=f"""
Analyze incident by querying logs directly. Workflow is triggered by an alert, so incident is already detected.

INPUT JSON includes only:
- service_name (string) => EVERY LogQL query MUST use this label.
- lookup_window_seconds (optional) => Duration to look back. Default is 900s.

STEPS:
1. Time Window Handling:
   - DO NOT calculate start/end times yourself.
   - Pass `lookup_window_seconds` to `query_loki` ONLY if you need to override the default.
   - `query_loki` handles all timestamp calculations.

2. Build LogQL queries (exclude info and debug levels):
   - ALWAYS include the service_name label: '{{service_name="<service_name>", level=~"error|warning|fatal|panic|warn"}}'
   - This is MANDATORY. NEVER drop the service_name label.
   - This captures error, warning, fatal, panic levels (excludes info and debug)
   - Alternative if regex doesn't work: Use log filter: '{{service_name="<service_name>"}} |~ "level.*(error|warn|fatal|panic)"'

3. Call tools:
   - ALWAYS call query_loki(log_query=<combined_query>). 
   - If you need a custom window, include lookup_window_seconds=<seconds>. 
   - DO NOT pass start or end — the tool calculates them automatically.

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
- Workflow triggered by alert => incident_detected=true, recommendation="proceed"
- Time Window: Let query_loki compute start/end. Do NOT invent timestamps.
- Query Syntax: MUST include '{{service_name="<service_name>", level=~"error|warning|fatal|panic|warn"}}'.
- Analysis: Count errors/warnings separately.
- Output: Return ONLY valid JSON. No markdown formatting, no extra text.
""",
    tools=[
        FunctionTool(func=query_loki)
    ]
)

