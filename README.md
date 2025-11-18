# Incident CoPilot
### Let your on-call engineers rest more

<p align="center">
  <img src="assets/incident_copilot.png" alt="Incident CoPilot overview" width="720">
</p>

Incident CoPilot is a production-ready multi-agent responder that turns noisy Grafana alerts into actionable root-cause analysis, proposed fixes, GitHub pull requests, and html-formatted on-call briefs without waiting for a human to run the playbook.

## The Pitch

### Problem
- On-call engineers still triage incidents manually: copy log links, guess the failure domain, write mitigation steps, and draft comms. Context switching during an outage costs minutes we do not have.

### Solution
- A chained set of Gemini-powered agents that ingest Grafana Loki logs the moment an alert fires, confirm if the issue is code-related, run repository searches, draft a fix, open a PR, and notify on-call engineers through Gmail with a closing briefing from the EmailWriter agent.

### Value
- Shrinks time-to-mitigation by making “identify => diagnose => patch => communicate” a single automated workflow.
- Keeps humans in control by surfacing structured evidence, proposed diffs, and ready-to-review pull requests instead of taking blind actions.
- Every run saves JSON artifacts and email transcripts so SREs can audit or resume the response later, and the EmailWriter agent always issues the final email.

### Track Relevance
- Agents are not ornamental; they decide whether to run code workflows, what files to patch, and when to block unsafe actions. A tiered model strategy (Gemini 2.5 Pro for reasoning, Flash Lite for speed) ensures optimal performance and cost-efficiency.

## Implementation

### Architecture Snapshot
- FastAPI webhook (`/webhook/trigger_agent`) accepts Grafana alerts (payload must include `service_name`; `lookup_window_seconds` is optional and defaults to 900 seconds/15 minutes) and starts an asynchronous session (`run_workflow` in `incident_copilot/agent.py`).
- The orchestrator chains Sequential + Conditional + Parallel agents:
  1. `IncidentDetectionAgent` queries Loki via a FunctionTool and produces the canonical incident JSON.
  2. `CodeAnalyzerAgent` (guarded) uses the GitHub MCP toolset to inspect repos only when the incident looks like a code regression.
  3. `RCAAgent` and `SuggestionAgent` run in parallel to speed up analysis.
  4. `SolutionGeneratorAgent` emits mitigations plus structured patch objects; `PRExecutorAgent` (branch => file => PR) consumes that patch.
  5. `EmailWriterAgent` builds an executive briefing, calls Gmail through `send_incident_email`, and triggers any configured `POST_PROCESS_URL` (e.g., webhook) in parallel. This ensures on-call engineers receive a summary and external systems are notified even if the guard skipped the incident.
- Outputs land in `output/` as JSON + rendered emails for auditability.

```
Grafana Alert
     │
     ▼
FastAPI Webhook ──► run_workflow()
     │
     ▼
IncidentDetectionAgent ──┬─► Conditional Code Analyzer ──► Solution + PR chain
                         └─► Parallel(RCAAgent, SuggestionAgent)
                                                │
                                                ▼
                                      EmailWriterAgent => Gmail + HTML formatter
                                                │
                                                ▼
                                      EmailWriterAgent => Gmail + HTML formatter
                                                │
                                                ▼
                                      Failover email + Post-Process Action (Parallel) + output artifacts
```

![Incident CoPilot Agent Workflow](assets/agent.png)

### Agent Roster (central ones)

| Agent | Purpose | Tools / Concepts |
| --- | --- | --- |
| `IncidentDetectionAgent` | Executes LogQL queries against Loki, classifies severity and incident type hints. Uses **Gemini 2.5 Pro** for high-fidelity log analysis. | FunctionTool => `tools.loki_client.query_loki` |
| `CodeAnalyzerAgent` | Launches the GitHub MCP server to search code and pull full files so patches reference real line numbers. Uses **Gemini 2.5 Pro** for deep code understanding. | MCP toolset, repo auto-detection |
| `RCAAgent` | Converts log-derived evidence into explicit hypotheses with confidence + affected components. Uses **Gemini 2.5 Flash Lite** for fast pattern matching. | Context-grounded reasoning only |
| `SolutionGeneratorAgent` | Generates mitigations and structured `patch.files_to_modify` payloads the PR workflow consumes. Uses **Gemini 2.5 Pro** for precise code generation. | JSON contract enforcement |
| `PRExecutorAgent` | Sequentially creates a branch, writes files, and opens a PR (skips gracefully if nothing to patch). Uses **Gemini 2.5 Flash Lite**. | GitHub REST API helpers, PR gate |
| `EmailWriterAgent` | Crafts the human-facing incident brief, calls Gmail, and triggers post-process actions (webhooks) in parallel. Uses **Gemini 2.5 Flash**. | `get_on_call_engineers`, `publish_incident_report` |

### Persistent Trace Logging
- The unified tracer plugin (`custom_plugins/event_tracer_plugin.py`) captures every agent callback in memory so predicates can reuse structured outputs, and—when Mongo credentials are supplied—also writes one MongoDB document per `invocation_id`.
- Each entry in `traces.<agent_name>` records `runStart`, `runEnd`, raw agent input/response, tool call arguments, tool results, and categorized errors, making it easy to replay decisions after the incident.
- The plugin buffers in-memory state and persists once an agent finishes, ensuring a single cohesive record per agent instead of fragmented snippets.
- Example document:

```
{
  "invocation_id": "abc123",
  "session_id": "session-1",
  "user": { "input": "Checkout errors > 5%" },
  "traces": {
    "IncidentDetectionAgent": [
      {
        "runStart": "...",
        "runEnd": "...",
        "agent_input": "...",
        "agent_response": "...",
        "tool_call": { "tool_name": "query_loki", "args": {...}, "start": "..." },
        "tool_result": { "tool_name": "query_loki", "result": {...}, "end": "..." },
        "errors": []
      }
    ],
    "EmailWriterAgent": [
      {
        "...": "..."
      }
    ]
  },
  "created_at": "...",
  "updated_at": "..."
}
```
- Configure the plugin via ADK’s plugin settings with your Mongo URI, database, and collection; once enabled every workflow automatically lands in that collection.

### Architecture Highlights
- **Multi-agent system (LLM, Sequential, Parallel):** Every stage is an LLM-backed agent; `SequentialAgent` orchestrates the run, `ParallelAgent` fans out RCA/Suggestion, and loop-style conditional wrappers gate optional steps (`conditional_code_analyzer`, `conditional_solution_pr_workflow`).
- **Tools (MCP + custom):** Agents call FunctionTools for Grafana Loki, Gmail, GitHub REST, and the GitHub MCP toolset (`search_code`, `get_file_contents`) so patches cite real code.
- **Sessions & Memory:** `InMemorySessionService` and `InMemoryMemoryService` maintain per-run state (`agent_responses`) so later agents reuse earlier outputs without re-querying systems.
- **Observability & Deployment:** `LoggingPlugin` streams every agent event to stdout, JSON artifacts land in `output/`, and `app.py` exposes a FastAPI webhook for deployment on Uvicorn/Cloud Run.
- **Persistent Mongo traces:** `custom_plugins/event_tracer_plugin.py` keeps per-agent history in session state and, when configured, mirrors the full run (user input + agent events + tool activity) into MongoDB for postmortems.
- **Safety & Guardrails:** Code-level predicates skip entire branches (incident response, code analyzer, solution/PR) when prior agent snapshots indicate a skip, so we avoid unnecessary LLM calls while keeping the workflow safe.

### Supporting Components
- `tools/email_html_formatter.py` converts the plain-text brief into a responsive HTML template with sections (incident summary, RCA, solution status, action plan, PR).
- `incident_copilot/github.py` centralizes branch/file/PR logic including repo auto-discovery, Base64 encoding, branch diff checks, and helpful error surfacing.

## Setup

### Prerequisites
- Python 3.11+
- pip + virtualenv (recommended)
- Access to Grafana Loki, GitHub, and Gmail APIs (service or test accounts)
- Node.js 18+ (required for the GitHub MCP server; Cloud Run installs it automatically via `packages.txt`, but install locally if you run agents on your machine)

### Telemetry Configuration
The system now supports pluggable telemetry providers for both logs and metrics.

**Logs:**
- Default: `loki`
- Env Var: `TELEMETRY_PROVIDER_LOGS=loki`
- Requires: `GRAFANA_HOST`, `GRAFANA_BASICAUTH` (optional)

**Metrics:**
- Default: `prometheus`
- Env Var: `TELEMETRY_PROVIDER_METRICS=prometheus`
- Requires: `PROMETHEUS_HOST` (or falls back to `GRAFANA_HOST`), `PROMETHEUS_BASICAUTH` (optional)

### Environment Variables (.env example)

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | Friendly label shown in ADK sessions |
| `GRAFANA_HOST`, `GRAFANA_BASICAUTH` | HTTPS endpoint + `user:password` used to query Loki |
| `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BASE_BRANCH`, `GIT_REPO_PATH` | Grants repo access for MCP + REST commits |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_USER_EMAIL` | OAuth credentials for Gmail send API |
| `ON_CALL_ENGINEERS` | JSON list of target emails (defaults to a single address) |
| `GEMINI_API_KEY` | API key for Gemini / Google Generative Language |
| `WEBHOOK_USER_ID` | Label applied to webhook-triggered sessions |
| `POST_PROCESS_URL` | Optional URL to trigger after the automated triage workflow (e.g., PagerDuty, Slack webhook). Receives incident JSON payload. |
| `TELEMETRY_PROVIDER_LOGS` | Provider for logs (default: `loki`). Currently supports `loki`. |
| `TELEMETRY_PROVIDER_METRICS` | Provider for metrics (default: `prometheus`). Currently supports `prometheus`. |
| `PROMETHEUS_HOST` | Base URL for Prometheus (e.g., `http://prometheus:9090`). |
| `LOOKUP_WINDOW_SECONDS` | Default lookup window (seconds) used when a request omits `lookup_window_seconds`; otherwise the webhook-provided value controls how far back to query logs. |
| `SAVE_OUTPUT` | When set to `true`/`1`, incident JSON artifacts are written to `output/`; otherwise they are skipped. |

Create the file:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # if you keep templates
```

### GitHub MCP helper
The Code Analyzer launches `@modelcontextprotocol/server-github` through `npx`. Install the dependency in this repo (locks live in `package-lock.json`):

```
npm install
```

Cloud Run installations use `packages.txt` (lists `nodejs` + `npm`) plus this `package.json` so buildpacks provision the same tooling automatically.

## Running The Workflow

### 1. Manual dry run from a REPL

```
python - <<'PY'
import asyncio
from incident_copilot.agent import run_workflow

async def demo():
    await run_workflow(
        user_id="cli_test",
        service_name="checkout-api",
        end_time="2025-11-16T15:00:00Z",
        lookup_window_seconds=3600
    )

asyncio.run(demo())
PY
```

### 2. Trigger via webhook (hook it to Grafana)

Webhook requests must provide `service_name` (the Grafana label you want in the LogQL query). `lookup_window_seconds` is optional; if omitted the webhook defaults to 900 seconds (15 minutes). The service treats the arrival timestamp as `end_time` and derives `start_time = end_time - lookup_window_seconds`.

```
uvicorn app:api --host 0.0.0.0 --port 8000

curl -X POST http://localhost:8000/webhook/trigger_agent \
  -H "Content-Type: application/json" \
  -d '{
        "title":"Checkout errors > 5%",
        "service_name":"checkout-api",
        "lookup_window_seconds":3600
      }'
```

 The endpoint stamps `service_name`, `user_id`, and the derived time window, then hands the payload to the orchestrator asynchronously so Grafana does not block.

### 3. Review artifacts
- If `SAVE_OUTPUT=true` in `.env`, `output/incident_<id>_<timestamp>.json` includes workflow summaries, agent responses, and email delivery metadata; otherwise these files are skipped.
- `output/*email.txt` lets you confirm what Gmail received.
- Logs in the terminal include per-agent events thanks to `LoggingPlugin`.

### 4. Run in ADK Web
1. Export the same environment variables you use locally (`GRAFANA_HOST`, `GITHUB_TOKEN`, `GMAIL_CLIENT_ID`, etc.) so ADK Web can access external services.
2. From the repo root, launch the web playground:
   ```
   adk web
   ```
3. In the browser, pick the `incident_copilot` app, then start a session with:
   ```
   {"service_name": "checkout-api", "lookup_window_seconds": 3600}
   ```
   The web UI will stream each agent’s reasoning, tool calls, and outputs in real time.

-## Testing & Quality
- Run `pytest` to execute the focused regression tests (HTML formatter, email helper status, workflow helpers).
- `tests/test_email_html_formatter.py` ensures section parsing renders correctly, preventing malformed executive briefs.
- `tests/test_email_helper_status.py` guarantees the email status cache behaves even when the LLM handles the tool call.
- For integration testing, point `GRAFANA_HOST` to a staging Loki instance and replay recorded incidents; every run is deterministic for the same logs.
- **Mock Prometheus:** Use `scripts/mock_prometheus.py` to simulate metrics without a live server.
  - Run: `python3 scripts/mock_prometheus.py`
  - Configure: `PROMETHEUS_HOST=http://localhost:9090`
  - Presets: Set `MOCK_CPU=high`, `MOCK_RAM=mid`, or `MOCK_NETWORK=low` to test different scenarios.

## Deployment

### Local Development
```bash
uvicorn app:api --reload
```

### Cloud Run Deployment

#### Prerequisites
- Google Cloud SDK installed and configured
- GCP project with billing enabled
- Cloud Run API enabled
- Container Registry API enabled (or Artifact Registry)

#### Option 1: Manual Deployment with gcloud

**Step 1: Prerequisites Setup**

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export SERVICE_ID=incident-copilot

gcloud config set project $PROJECT_ID

gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

`packages.txt` (repo root) makes the buildpack apt-install `nodejs`/`npm`, so `npx` can launch the GitHub MCP server. `Procfile` tells the runtime to start FastAPI via `uvicorn app:api --host 0.0.0.0 --port $PORT`.

**Step 2: Build & Deploy from Source (Cloud Run)**

```bash
gcloud run deploy $SERVICE_ID \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900 \
  --max-instances 10 \
  --min-instances 0
```

**Step 3: Configure Environment Variables**

Set non-sensitive environment variables:

```bash
gcloud run services update $SERVICE_ID \
  --region $REGION \
  --set-env-vars "APP_NAME=incident_copilot,WEBHOOK_USER_ID=grafana_webhook,LOOKUP_WINDOW_SECONDS=3600,GITHUB_BASE_BRANCH=main,GIT_BASE_BRANCH=main"
```

**Step 4: Set Up Secrets (Recommended for Sensitive Values)**

Create secrets in Secret Manager:

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

echo -n "username:password" | gcloud secrets create grafana-basicauth --data-file=-
echo -n "your-github-token" | gcloud secrets create github-token --data-file=-
echo -n "your-gmail-client-id" | gcloud secrets create gmail-client-id --data-file=-
echo -n "your-gmail-client-secret" | gcloud secrets create gmail-client-secret --data-file=-
echo -n "your-gmail-refresh-token" | gcloud secrets create gmail-refresh-token --data-file=-
echo -n "your-gmail-user-email" | gcloud secrets create gmail-user-email --data-file=-
echo -n "your-github-repo" | gcloud secrets create github-repo --data-file=-
echo -n '["email1@example.com","email2@example.com"]' | gcloud secrets create on-call-engineers --data-file=-
echo -n "https://your-grafana-instance.com" | gcloud secrets create grafana-host --data-file=-
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-
```

Grant Cloud Run service account access to secrets:

```bash
export SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding grafana-basicauth \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding github-token \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gmail-client-id \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gmail-client-secret \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gmail-refresh-token \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gmail-user-email \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding github-repo \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding on-call-engineers \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding grafana-host \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

Update Cloud Run service to use secrets:

```bash
gcloud run services update $SERVICE_ID \
  --region $REGION \
  --update-secrets \
    GRAFANA_BASICAUTH=grafana-basicauth:latest,\
    GITHUB_TOKEN=github-token:latest,\
    GMAIL_CLIENT_ID=gmail-client-id:latest,\
    GMAIL_CLIENT_SECRET=gmail-client-secret:latest,\
    GMAIL_REFRESH_TOKEN=gmail-refresh-token:latest,\
    GMAIL_USER_EMAIL=gmail-user-email:latest,\
    GITHUB_REPO=github-repo:latest,\
    ON_CALL_ENGINEERS=on-call-engineers:latest,\
    GRAFANA_HOST=grafana-host:latest,\
    GEMINI_API_KEY=gemini-api-key:latest
```

**Step 5: Verify Deployment**

```bash
export SERVICE_URL=$(gcloud run services describe $SERVICE_ID \
  --region $REGION \
  --format="value(status.url)")

curl -X POST $SERVICE_URL/webhook/trigger_agent \
  -H "Content-Type: application/json" \
  -d '{"title":"Test incident"}'

gcloud run services logs read $SERVICE_ID --region $REGION --limit 50
```

**Alternative: Set All Environment Variables Directly (Not Recommended for Production)**

If you prefer not to use Secret Manager, you can set all variables directly (less secure):

```bash
gcloud run services update $SERVICE_ID \
  --region $REGION \
  --set-env-vars \
    "APP_NAME=incident_copilot,\
    WEBHOOK_USER_ID=grafana_webhook,\
    LOOKUP_WINDOW_SECONDS=3600,\
    GITHUB_BASE_BRANCH=main,\
    GIT_BASE_BRANCH=main,\
    GRAFANA_HOST=https://your-grafana-instance.com,\
    GRAFANA_BASICAUTH=username:password,\
    GITHUB_TOKEN=your-github-token,\
    GITHUB_REPO=owner/repo-name,\
    GMAIL_CLIENT_ID=your-client-id,\
    GMAIL_CLIENT_SECRET=your-client-secret,\
    GMAIL_REFRESH_TOKEN=your-refresh-token,\
    GMAIL_USER_EMAIL=your-email@gmail.com,\
    ON_CALL_ENGINEERS=[\"email1@example.com\",\"email2@example.com\"],\
    GEMINI_API_KEY=your-gemini-api-key"
```

#### Configuration

The FastAPI app is stateless; Gemini + Google ADK handle runtime state in memory per session. Ensure the Cloud Run service has:
- **Memory:** At least 2Gi (recommended: 4Gi for complex workflows)
- **CPU:** At least 2 vCPU
- **Timeout:** 900 seconds (15 minutes) for long-running agent workflows
- **Concurrency:** 1-10 requests per instance (adjust based on workload)
- **Min/Max instances:** Configure based on expected traffic

#### Environment Variables

Set all required environment variables (see Setup section) via:
- `gcloud run services update` with `--set-env-vars` (for non-sensitive values)
- GCP Secret Manager (recommended for sensitive credentials like tokens, passwords)

#### Network Requirements

Cloud Run instances need outbound HTTPS access to:
- Grafana Loki (your `GRAFANA_HOST`)
- GitHub API (`api.github.com`)
- Gmail API (`gmail.googleapis.com`)
- Gemini API (`generativelanguage.googleapis.com`)

No VPC configuration needed unless your Grafana instance is private.

#### Testing the Deployment

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe incident-copilot --region $REGION --format="value(status.url)")

# Test the webhook
curl -X POST $SERVICE_URL/webhook/trigger_agent \
  -H "Content-Type: application/json" \
  -d '{"title":"Test incident"}'
```

#### Monitoring

- View logs: `gcloud run services logs read incident-copilot --region $REGION`
- Monitor in Cloud Console: Cloud Run => incident-copilot => Logs/Metrics
- Set up alerting for failed workflows in Cloud Monitoring

## Bonus Hooks
- **Gemini usage:** The architecture demonstrates a sophisticated tiered model strategy. `Gemini 2.5 Pro` handles complex reasoning (Incident Detection, Code Analysis, Solution Generation), while `Gemini 2.5 Flash/Flash-Lite` handles high-volume/lower-complexity tasks (RCA, PR creation, Emailing). This optimizes for both intelligence and latency/cost.
- **Tooling & Observability:** Loki client, GitHub REST helpers, Gmail sender, workflow gates, and HTML templates are each encapsulated in `tools/` with docstrings to explain their behavior.
- **Deployment reproducibility:** The webhook + CLI flows above show exactly how judges can rerun the project; no hidden services required.
- **Video-ready storyline:** Demo script “send Grafana alert => auto RCA => PR link + HTML email” is already storyboarded by the README sections, making it easy to narrate a short video if desired.

## Troubleshooting
- Missing `GITHUB_REPO`: Code Analyzer quietly sets `mcp_available=false`; patch generation degrades to log-based suggestions instead of failing.
- Gmail refresh token errors (`invalid_grant`): check the helper logs; instructions point you to regenerate the token.
- Loki access denied: confirm `GRAFANA_BASICAUTH` is `username:password` (the helper encodes it for you).

---

Incident CoPilot packages the entire incident lifecycle (detection, RCA, fix generation, automated code changes, and comms) into a single, auditable workflow that teams can run anywhere Python 3.11 and Gemini are available.

