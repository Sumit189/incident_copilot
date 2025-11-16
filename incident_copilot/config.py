"""
Configuration for Incident CoPilot agents and tools.
"""

import os
from google.genai import types

# App Configuration
APP_NAME = os.getenv("APP_NAME", "incident_copilot")

# Model Configuration
DEFAULT_MODEL = "gemini-2.5-flash-lite"

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
SERVICE_NAME = os.getenv("SERVICE_NAME", "talestitch")
WEBHOOK_USER_ID = os.getenv("WEBHOOK_USER_ID", "grafana_webhook")

# Incident Lookup Window Configuration
# How far back to look for logs before the incident start time (in seconds)
# Default: 3600 seconds (1 hour)
# Example: If incident starts at 11:00 AM and LOOKUP_WINDOW_SECONDS=3600, query logs from 10:00 AM to 11:00 AM
LOOKUP_WINDOW_SECONDS = int(os.getenv("LOOKUP_WINDOW_SECONDS", "3600"))
