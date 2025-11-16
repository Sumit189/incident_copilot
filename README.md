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
- A chained set of Gemini-powered agents that ingest Grafana Loki logs the moment an alert fires, confirm if the issue is code-related, run repository searches, draft a fix, open a PR, and notify on-call engineers through Gmail with failover guarantees.

### Value
- Shrinks time-to-mitigation by making “identify → diagnose → patch → communicate” a single automated workflow.
- Keeps humans in control by surfacing structured evidence, proposed diffs, and ready-to-review pull requests instead of taking blind actions.
- Every run saves JSON artifacts and email transcripts so SREs can audit or resume the response later, and a built-in failover sender guarantees on-call notifications even if the Email Writer agent hiccups.

### Track Relevance
- Agents are not ornamental; they decide whether to run code workflows, what files to patch, and when to block unsafe actions. Gemini 2.5 Flash Lite is the core reasoning engine for every step, showing meaningful use of the platform.

## Implementation

### Architecture Snapshot
- FastAPI webhook (`/webhook/trigger_agent`) accepts Grafana alerts and starts an asynchronous session (`run_workflow` in `incident_copilot/agent.py`).
- The orchestrator chains Sequential + Conditional + Parallel agents:
  1. `IncidentDetectionAgent` queries Loki via a FunctionTool and produces the canonical incident JSON.
  2. `CodeAnalyzerAgent` (guarded) uses the GitHub MCP toolset to inspect repos only when the incident looks like a code regression.
  3. `RCAAgent` and `SuggestionAgent` run in parallel to speed up analysis.
  4. `SolutionGeneratorAgent` emits mitigations plus structured patch objects; `PRExecutorAgent` (branch → file → PR) consumes that patch.
  5. `EmailWriterAgent` builds an executive briefing, calls Gmail through `send_incident_email` only when the guard has confirmed an incident, and the failover helper re-sends if Gmail was unreachable.
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
                                      EmailWriterAgent → Gmail + HTML formatter
                                                │
                                                ▼
                                      Failover email + output artifacts
```

![Incident CoPilot Agent Workflow](assets/agent.png)

### Agent Roster (central ones)

| Agent | Purpose | Tools / Concepts |
| --- | --- | --- |
| `IncidentDetectionAgent` | Executes LogQL queries against Loki, classifies severity and incident type hints. | FunctionTool → `tools.loki_client.query_loki` |
| `CodeAnalyzerAgent` | Launches the GitHub MCP server to search code and pull full files so patches reference real line numbers. | MCP toolset, repo auto-detection |
| `RCAAgent` | Converts log-derived evidence into explicit hypotheses with confidence + affected components. | Context-grounded reasoning only |
| `SolutionGeneratorAgent` | Generates mitigations and structured `patch.files_to_modify` payloads the PR workflow consumes. | JSON contract enforcement |
| `PRExecutorAgent` | Sequentially creates a branch, writes files, and opens a PR (skips gracefully if nothing to patch). | GitHub REST API helpers, PR gate |
| `EmailWriterAgent` | Crafts the human-facing incident brief, calls Gmail, and triggers HTML rendering. | `get_on_call_engineers`, `send_incident_email` |

### Course Concepts Demonstrated
- **Multi-agent system (LLM, Sequential, Parallel):** Every stage is an LLM-backed agent; `SequentialAgent` orchestrates the run, `ParallelAgent` fans out RCA/Suggestion, and loop-style conditional wrappers gate optional steps (`conditional_code_analyzer`, `conditional_solution_pr_workflow`).
- **Tools (MCP + custom):** Agents call FunctionTools for Grafana Loki, Gmail, GitHub REST, workflow gates, and the GitHub MCP toolset (`search_code`, `get_file_contents`) so patches cite real code.
- **Sessions & Memory:** `InMemorySessionService` and `InMemoryMemoryService` maintain per-run state (`agent_responses`, fallbacks) so later agents, including the failover emailer, reuse earlier outputs without re-querying systems.
- **Observability & Deployment:** `LoggingPlugin` streams every agent event to stdout, JSON artifacts land in `output/`, and `app.py` exposes a FastAPI webhook for deployment on Uvicorn/Cloud Run.
- **Safety & Guardrails:** PR workflow gates prevent empty PRs; email failover ensures humans still get notified; conditional wrappers (`workflow_guard`, `code_analyzer_conditional`, `solution_pr_conditional`) stop the cascade when detection says “no incident”.

### Supporting Components
- `tools/email_html_formatter.py` converts the plain-text brief into a responsive HTML template with sections (incident summary, RCA, solution status, action plan, PR).
- `incident_copilot/email_failover.py` reconstructs an email body from stored agent JSON, then calls the helper if the Email Writer skipped.
- `incident_copilot/github.py` centralizes branch/file/PR logic including repo auto-discovery, Base64 encoding, branch diff checks, and helpful error surfacing.
- `tools/workflow_control.py` lets agents block further automation (e.g., disable PR creation when configuration is missing).

## Setup

### Prerequisites
- Python 3.11+
- pip + virtualenv (recommended)
- Access to Grafana Loki, GitHub, and Gmail APIs (service or test accounts)
- Node.js 18+ only if you plan to run the GitHub MCP server locally

### Environment Variables (.env example)

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | Friendly label shown in ADK sessions |
| `GRAFANA_HOST`, `GRAFANA_BASICAUTH` | HTTPS endpoint + `user:password` used to query Loki |
| `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BASE_BRANCH`, `GIT_REPO_PATH` | Grants repo access for MCP + REST commits |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_USER_EMAIL` | OAuth credentials for Gmail send API |
| `ON_CALL_ENGINEERS` | JSON list of target emails (defaults to a single address) |
| `SERVICE_NAME`, `WEBHOOK_USER_ID` | Labels used in detection + alerting |
| `LOOKUP_WINDOW_SECONDS` | How far back to look around the incident timestamp |

Create the file:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # if you keep templates
```

### Optional GitHub MCP setup
The Code Analyzer spins up `@modelcontextprotocol/server-github` via `npx`. Install Node dependencies once:

```
npm install -g @modelcontextprotocol/server-github
```

## Running The Workflow

### 1. Manual dry run from a REPL

```
python - <<'PY'
import asyncio
from incident_copilot.agent import run_workflow

async def demo():
    await run_workflow(
        user_id="cli_test",
        service="checkout-api",
        start_time="2025-11-16T15:00:00Z"
    )

asyncio.run(demo())
PY
```

### 2. Trigger via webhook (hook it to Grafana)

```
uvicorn app:api --host 0.0.0.0 --port 8000

curl -X POST http://localhost:8000/webhook/trigger_agent \
  -H "Content-Type: application/json" \
  -d '{"title":"Checkout errors > 5%"}'
```

The endpoint stamps `service`, `user_id`, and `start_time`, then hands the payload to the orchestrator asynchronously so Grafana does not block.

### 3. Review artifacts
- `output/incident_<id>_<timestamp>.json` includes workflow summaries, agent responses, and email delivery metadata.
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
   {"start_time": "2025-11-16T15:00:00Z"}
   ```
   The web UI will stream each agent’s reasoning, tool calls, and outputs in real time.

## Testing & Quality
- Run `pytest` to execute the focused regression tests (HTML formatter, failover sender, workflow helpers).
- `tests/test_email_html_formatter.py` ensures section parsing renders correctly, preventing malformed executive briefs.
- `tests/test_email_failover.py` and `tests/test_email_helper_status.py` guarantee the fallback email always has the mandatory sections and the status cache behaves.
- For integration testing, point `GRAFANA_HOST` to a staging Loki instance and replay recorded incidents; every run is deterministic for the same logs.

## Deployment Notes
- Local: `uvicorn app:api --reload` handles most demos.
- Container: bake `.venv`, install requirements, and inject environment variables/secrets via your orchestrator (GCP Secret Manager, Doppler, etc.).
- Cloud Run/App Engine: the FastAPI app is stateless; Gemini + Google ADK handle runtime state in memory per session.
- Reproducing deployment: ensure the environment provides outbound HTTPS to Grafana, GitHub, Gmail, and Gemini; no additional infrastructure is required.

## Bonus Hooks
- **Gemini usage:** Every agent declares `Gemini(model="gemini-2.5-flash-lite")` plus shared retry policy so the submission clearly exercises Gemini for reasoning, code generation, and summarization.
- **Tooling & Observability:** Loki client, GitHub REST helpers, Gmail sender, workflow gates, and HTML templates are each encapsulated in `tools/` with docstrings to explain their behavior.
- **Deployment reproducibility:** The webhook + CLI flows above show exactly how judges can rerun the project; no hidden services required.
- **Video-ready storyline:** Demo script “send Grafana alert → auto RCA → PR link + HTML email” is already storyboarded by the README sections, making it easy to narrate a short video if desired.

## Troubleshooting
- Missing `GITHUB_REPO`: Code Analyzer quietly sets `mcp_available=false`; patch generation degrades to log-based suggestions instead of failing.
- Gmail refresh token errors (`invalid_grant`): check the helper logs; instructions point you to regenerate the token.
- “PR workflow blocked”: see `tools/workflow_control.py`; agents might have called `block_pr_workflow` because the Solution Agent produced no patch or repo creds were absent.
- Loki access denied: confirm `GRAFANA_BASICAUTH` is `username:password` (the helper encodes it for you).

---

Incident CoPilot packages the entire incident lifecycle (detection, RCA, fix generation, automated code changes, and comms) into a single, auditable workflow that teams can run anywhere Python 3.11 and Gemini are available.

