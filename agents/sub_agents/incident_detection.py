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
   - **Secondary Source (Conditional)**: Fetch METRICS *only if*:
     * Logs are inconclusive or suggest a resource issue (e.g., "OOMKilled", "Timeout")
     * OR you see authentication failures and need to check for spikes (fetch auth_failure_rate)
     * OR you see rate limiting errors and need to check patterns (fetch rate_limit_errors)
     - Do NOT fetch metrics by default.
     - If fetching metrics, fetch ONLY the relevant one (e.g., memory for OOM, auth_failure_rate for auth failures).
   - **Goal**: Get enough data to detect the incident in **1 or 2 tool calls maximum**. Do not loop.

3. Analyze Data:
   - Logs: Count errors/warnings, identify patterns/symptoms.
   - Metrics: Look for spikes, saturation, or anomalies correlated with log errors.
   - Severity: Critical (service down/high errors) | High (user impact) | Medium (partial) | Low (minor).
   
   **INCIDENT DETECTION THRESHOLD**:
   - Single isolated error (1 error log) with no pattern/repetition and no metric anomalies → likely NOT an incident (transient noise), set incident_detected=false
   - Multiple errors (2+), error patterns, or metric anomalies → likely an incident, set incident_detected=true
   
   **SPECIAL CLASSIFICATION RULES** (apply BEFORE general classification):
   - **Authentication failures with patterns**: If you see 2+ "Authentication failed" errors OR auth_failure_rate metric spiking (e.g., 0.02 → 0.35 → 0.50) → classify as code_issue. Rationale: Spikes/patterns indicate bugs in auth logic (wrong validation, token handling). Isolated single failures might be wrong credentials (config_issue), but patterns indicate code bugs.
   - **Config parsing errors**: If error mentions "parse", "parsing", "parse config", "failed to parse" → classify as code_issue. Rationale: The parsing code itself has a bug, not the config values.

4. Classification Guidelines:
   
   **infrastructure_issue**: Failures caused by infrastructure or external dependencies.
   - Examples: network timeouts, DNS issues, connection pool starvation, CPU or memory pressure on hosts, database connectivity failures, flaky upstream services, and general network instability.
   
   **code_issue**: Failures rooted in the application's own logic or implementation.
   - Examples: exceptions like NPE (NullPointerException), OOB (ArrayIndexOutOfBounds), type errors, wrong validation logic, incorrect conditional flows, broken auth logic, faulty rate limiting logic, memory leaks introduced by code, buggy retry loops, and config parsing errors caused by code defects.
   - In short: if the code behaved incorrectly even with correct inputs and correct config, it belongs here.
   
   **config_issue**: Failures caused by incorrect or missing configuration.
   - Examples: invalid config values, wrong environment variables, missing config files, incorrect feature flags, misconfigured timeouts, wrong API keys, or limits that cause the system to misbehave even though the code itself is fine.
   
   **unknown**: Use only when symptoms do not clearly map to any category after reviewing logs and behavior.

5. Return JSON ONLY (no text, no questions):
{{
  "incident_detected": true|false,
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
  "recommendation": "proceed|dismiss"
}}

CRITICAL RULES:
- If logs/metrics confirm the alert, set incident_detected=true, recommendation="proceed".
- If logs/metrics show NO significant errors or anomalies matching the alert (false positive), set incident_detected=false, recommendation="dismiss".
- **Single isolated error with no pattern → incident_detected=false (transient noise)**

- **Classification Decision Tree** (apply in order - check each rule before moving to next):
  1. **"Failed to parse config", "parsing error", "parse config", "config parsing"** → code_issue (parsing code has bugs), NOT config_issue. This is CRITICAL: any error mentioning "parse" or "parsing" in relation to config is a code bug.
  2. **Authentication failures with spikes/patterns** → code_issue (broken auth logic), NOT config_issue. 
     - Check: If you see 2+ "Authentication failed" errors OR auth_failure_rate metric increasing/spiking (e.g., 0.02 → 0.35 → 0.50) → code_issue
     - Rationale: Multiple failures or spikes indicate a code bug in authentication logic (e.g., wrong validation, token handling bug). Wrong credentials would cause isolated failures, not patterns/spikes.
     - CRITICAL: Even if error message says "Invalid credentials", if there's a pattern (2+ errors) or metric spike, classify as code_issue. Check both logs AND metrics for authentication failures.
  3. **Rate limiting errors with increasing patterns** → code_issue (faulty rate limiting logic), NOT infrastructure_issue (quota exhaustion would be different symptoms)
  4. **Network timeouts, DNS issues, connection pool starvation, external service failures** → infrastructure_issue
  5. **Exceptions (NPE, OOB, type errors), wrong validation, memory leaks in code, buggy retry loops** → code_issue
  6. **Invalid config values (NOT parsing errors), wrong env vars, missing config files, misconfigured timeouts, wrong API keys** → config_issue
  7. **Unclear after analysis** → unknown

- **Key Distinctions**:
  * Authentication: **Spike/pattern in failures (2+ errors OR increasing auth_failure_rate metric)** = code_issue (logic bug), isolated single failure = config_issue (wrong creds). If you see multiple "Authentication failed" errors or auth_failure_rate increasing, classify as code_issue.
  * Rate limiting: Increasing errors = code_issue (logic bug), quota exhaustion = infrastructure_issue
  * Config: "parse/parsing" in error = code_issue, "invalid/wrong/missing" = config_issue

- Time Window: Let tool compute start/end. Do NOT invent timestamps.
- Log Query Syntax: MUST include '{{service_name="<service_name>", level=~"error|warning|fatal|panic|warn"}}'.
- Output: Return ONLY valid JSON. No markdown formatting, no extra text.
""",
    tools=[
        FunctionTool(func=fetch_telemetry)
    ]
)
