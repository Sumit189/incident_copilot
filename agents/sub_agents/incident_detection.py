from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini
from tools.telemetry_tool import fetch_telemetry
from agents.config import RETRY_CONFIG, LOOKUP_WINDOW_SECONDS, BEST_MODEL
from agents.utils.tool_config import get_tool_config

incident_detection_agent = LlmAgent(
    model=Gemini(
        model=BEST_MODEL,
        retry_options=RETRY_CONFIG,
        tool_config=get_tool_config(allowed_function_names=["fetch_telemetry"]),
    ),
    name="IncidentDetectionAgent",
    description="Analyze incident by querying logs directly (workflow triggered by alert).",
    instruction=f"""
Analyze incident by querying telemetry (logs and metrics). Workflow is triggered by an alert, so incident is already detected.

INPUT JSON includes only:
- service_name (string) => EVERY query MUST use this label.
- lookup_window_seconds (optional) => Duration to look back. Default is 900s.

STEPS:
1. Time Window Handling:
   - DO NOT calculate start/end times yourself.
   - Pass `lookup_window_seconds` to `fetch_telemetry` ONLY if you need to override the default.
   - The tool handles all timestamp calculations.

2. Fetch Telemetry (MINIMIZE CALLS):
   - **Primary Source**: Fetch LOGS first. They usually contain the root cause.
     - Query: '{{service_name="<service_name>", level=~"error|warning|fatal|panic|warn"}}'
     - Call `fetch_telemetry(query_type="logs", ...)`
   - **Secondary Source (Conditional)**: Fetch METRICS *only if* logs are inconclusive or suggest a resource issue (e.g., "OOMKilled", "Timeout").
     - Do NOT fetch metrics by default.
     - If fetching metrics, fetch ONLY the relevant one (e.g., memory for OOM).
   - **Goal**: Get enough data to detect the incident in **1 or 2 tool calls maximum**. Do not loop.

3. Analyze Data:
   - Logs: Count errors/warnings, identify patterns/symptoms.
   - Metrics: Look for spikes, saturation, or anomalies correlated with log errors.
   - Severity: Critical (service down/high errors) | High (user impact) | Medium (partial) | Low (minor).

4. Return JSON ONLY (no text, no questions):
{{
  "incident_detected": true,
  "severity": "Critical|High|Medium|Low",
  "affected_services": ["<extracted from stream_labels or metrics>"],
  "time_window": {{"start": "<query_start_time>", "end": "<end_time>"}},
  "initial_symptoms": ["<symptom from logs/metrics>"],
  "error_summary": {{
    "total_errors": <count from error/fatal/panic logs>,
    "total_warnings": <count from warning logs>,
    "error_types": ["<type from error logs>"],
    "warning_types": ["<type from warning logs>"],
    "peak_error_time": "<timestamp>",
    "metric_anomalies": ["<description of metric spikes>"]
  }},
  "incident_type_hint": "code_issue|config_issue|infrastructure_issue|unknown",
  "log_query_used": "<query used>",
  "recommendation": "proceed"
}}

CRITICAL RULES:
- Workflow triggered by alert => incident_detected=true, recommendation="proceed"
- Time Window: Let tool compute start/end. Do NOT invent timestamps.
- Log Query Syntax: MUST include '{{service_name="<service_name>", level=~"error|warning|fatal|panic|warn"}}'.
- Output: Return ONLY valid JSON. No markdown formatting, no extra text.
""",
    tools=[
        FunctionTool(func=fetch_telemetry)
    ]
)

