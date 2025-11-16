import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from incident_copilot.agent import run_workflow
from incident_copilot.config import SERVICE_NAME, WEBHOOK_USER_ID

logger = logging.getLogger("incident_copilot.webhook")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

api = FastAPI(
    title="Incident CoPilot Webhook",
    version="1.0.0",
    description="Webhook endpoint for triggering the Incident CoPilot workflow from Grafana alerts.",
)


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_non_empty(source: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_service(_: Dict[str, Any]) -> str:
    return SERVICE_NAME or "unknown-service"


def _resolve_user_id(_: Dict[str, Any]) -> str:
    return WEBHOOK_USER_ID or "grafana_webhook"


async def _run_workflow_task(user_id: str, service: str, start_time: str) -> None:
    try:
        await run_workflow(
            user_id=user_id,
            service=service,
            start_time=start_time,
        )
    except Exception:  # pragma: no cover - logged for observability
        logger.exception(
            "Incident workflow failed for service=%s user_id=%s start_time=%s",
            service,
            user_id,
            start_time,
        )


def _default_dispatcher(*, user_id: str, service: str, start_time: str, payload: Dict[str, Any]):
    logger.info(
        "Grafana webhook accepted for service=%s user_id=%s start_time=%s status=%s",
        service,
        user_id,
        start_time,
        payload.get("status"),
    )
    return asyncio.create_task(_run_workflow_task(user_id, service, start_time))


workflow_dispatcher = _default_dispatcher


@api.post("/webhook/trigger_agent", status_code=202)
async def grafana_webhook(payload: Dict[str, Any]) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body required")

    service = _resolve_service(payload)
    user_id = _resolve_user_id(payload)
    start_time = _iso_now_utc()

    workflow_dispatcher(user_id=user_id, service=service, start_time=start_time, payload=payload)

    return JSONResponse(
        {
            "status": "accepted",
            "service": service,
            "user_id": user_id,
            "start_time": start_time,
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
