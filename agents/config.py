"""
Configuration for Incident CoPilot agents and tools.
"""

import os
from google.genai import types

# App Configuration
APP_NAME = os.getenv("APP_NAME", "agents")

# Model Configuration
DEFAULT_MODEL = "gemini-2.5-flash-lite"
MID_MODEL = "gemini-2.5-flash"
BEST_MODEL = "gemini-2.5-pro"

# Retry Configuration for all agents
RETRY_CONFIG = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

# Grafana Loki Configuration
GRAFANA_HOST = os.getenv("GRAFANA_HOST", "")
GRAFANA_BASICAUTH = os.getenv("GRAFANA_BASICAUTH", "")

# Email Configuration
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
GMAIL_USER_EMAIL = os.getenv("GMAIL_USER_EMAIL", "")

# On-Call Engineers
ON_CALL_ENGINEERS_JSON = os.getenv("ON_CALL_ENGINEERS", '["sumit.18.paul@gmail.com"]')

# GitHub Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")

# Git Configuration
GIT_REPO_PATH = os.getenv("GIT_REPO_PATH", ".")
GIT_BASE_BRANCH = os.getenv("GIT_BASE_BRANCH", "main")

# Service/App Name Configuration
WEBHOOK_USER_ID = os.getenv("WEBHOOK_USER_ID", "grafana_webhook")
POST_PROCESS_URL = os.getenv("POST_PROCESS_URL", "")

# Incident Lookup Window Configuration
# Default window (seconds) used when the webhook omits `lookup_window_seconds`.
# Default: 900 seconds (15 minutes). Override via env if a longer window is needed.
LOOKUP_WINDOW_SECONDS = int(os.getenv("LOOKUP_WINDOW_SECONDS", "900"))

# Output Configuration
SAVE_OUTPUT = os.getenv("SAVE_OUTPUT", "false").lower() in ("1", "true", "yes")

# Telemetry Configuration
TELEMETRY_PROVIDER_LOGS = os.getenv("TELEMETRY_PROVIDER_LOGS", "loki")
TELEMETRY_PROVIDER_METRICS = os.getenv("TELEMETRY_PROVIDER_METRICS", "prometheus")
PROMETHEUS_HOST = os.getenv("PROMETHEUS_HOST", "")
PROMETHEUS_BASICAUTH = os.getenv("PROMETHEUS_BASICAUTH", "")
