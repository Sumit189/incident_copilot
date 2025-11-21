import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Set

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse

from agents.orchestrator import run_workflow
from agents.config import LOOKUP_WINDOW_SECONDS, WEBHOOK_USER_ID

_active_tasks: Set[asyncio.Task] = set()

logger = logging.getLogger("incident_copilot.webhook")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

api = FastAPI(
    title="Incident CoPilot Webhook",
    version="1.0.0",
    description="Webhook endpoint for triggering the Incident CoPilot workflow from Grafana alerts.",
)

API_KEY_NAME = "X-Webhook-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    expected_key = os.getenv("WEBHOOK_API_KEY")
    if not expected_key:
        logger.error("WEBHOOK_API_KEY environment variable is not set. Webhook is disabled.")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Webhook security not configured.",
        )

    if api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Could not validate credentials",
        )
    return api_key


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_user_id(_: Dict[str, Any]) -> str:
    return WEBHOOK_USER_ID or "grafana_webhook"


def _require_service_name(payload: Dict[str, Any]) -> str:
    raw = payload.get("service_name")
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(status_code=400, detail="service_name is required")
    return raw.strip()


def _parse_lookup_window(payload: Dict[str, Any]) -> int:
    raw = payload.get("lookup_window_seconds")
    if raw is None:
        return LOOKUP_WINDOW_SECONDS

    try:
        lookup = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="lookup_window_seconds must be an integer representing seconds",
        )

    if lookup <= 0:
        raise HTTPException(
            status_code=400,
            detail="lookup_window_seconds must be greater than zero",
        )

    return lookup


async def _run_workflow_task(user_id: str, service_name: str, end_time: str, lookup_window_seconds: int) -> None:
    try:
        await run_workflow(
            user_id=user_id,
            service_name=service_name,
            end_time=end_time,
            lookup_window_seconds=lookup_window_seconds,
        )
    except Exception:  # pragma: no cover - logged for observability
        logger.exception(
            "Incident workflow failed for service=%s user_id=%s end_time=%s lookup_window_seconds=%s",
            service_name,
            user_id,
            end_time,
            lookup_window_seconds,
        )
    finally:
        current_task = asyncio.current_task()
        if current_task and current_task in _active_tasks:
            _active_tasks.discard(current_task)


def _default_dispatcher(
    *, user_id: str, service_name: str, end_time: str, lookup_window_seconds: int, payload: Dict[str, Any]
) -> asyncio.Task:
    logger.info(
        "Grafana webhook accepted for service=%s user_id=%s end_time=%s lookup_window_seconds=%s status=%s",
        service_name,
        user_id,
        end_time,
        lookup_window_seconds,
        payload.get("status"),
    )
    task = asyncio.create_task(
        _run_workflow_task(user_id, service_name, end_time, lookup_window_seconds)
    )
    _active_tasks.add(task)
    return task


workflow_dispatcher = _default_dispatcher


@api.post("/webhook/trigger_agent", status_code=202, dependencies=[Depends(verify_api_key)])
async def grafana_webhook(payload: Dict[str, Any]) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body required")
    
    service_name = _require_service_name(payload)
    user_id = _resolve_user_id(payload)
    end_time = _iso_now_utc()
    lookup_window_seconds = _parse_lookup_window(payload)

    task = workflow_dispatcher(
        user_id=user_id,
        service_name=service_name,
        end_time=end_time,
        lookup_window_seconds=lookup_window_seconds,
        payload=payload,
    )

    return JSONResponse(
        {
            "status": "accepted",
            "service_name": service_name,
            "user_id": user_id,
            "end_time": end_time,
            "lookup_window_seconds": lookup_window_seconds,
        },
        status_code=202,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:api",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False,
    )
