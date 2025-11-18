from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from tools.telemetry.factory import TelemetryFactory
from agents.config import LOOKUP_WINDOW_SECONDS

def _normalize_iso(ts: str) -> str:
    ts = ts.strip()
    if ts.isdigit():
        parsed = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    else:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def fetch_telemetry(
    query_type: str,
    query: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    lookup_window_seconds: Optional[int] = None,
    step: Optional[int] = 15
) -> List[Dict[str, Any]]:
    """
    Fetch telemetry data (logs or metrics) from the configured provider.

    Args:
        query_type: "logs" or "metrics".
        query: The query string (LogQL for logs, PromQL for metrics).
        start: Start time (ISO 8601). If omitted, calculated from end - lookup_window.
        end: End time (ISO 8601). If omitted, defaults to now.
        lookup_window_seconds: Lookback window in seconds if start is not provided.
        step: Step size in seconds (only for metrics).

    Returns:
        List of results.
    """
    if query_type not in ["logs", "metrics"]:
        raise ValueError("query_type must be 'logs' or 'metrics'")

    # Time window calculation
    lookup = lookup_window_seconds or LOOKUP_WINDOW_SECONDS
    
    end_iso = (
        _normalize_iso(end)
        if end and end.strip()
        else datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    if start and start.strip():
        start_iso = _normalize_iso(start)
    else:
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        start_dt = end_dt - timedelta(seconds=lookup)
        start_iso = start_dt.isoformat().replace("+00:00", "Z")

    # Get provider
    if query_type == "logs":
        provider = TelemetryFactory.get_logs_provider()
    else:
        provider = TelemetryFactory.get_metrics_provider()

    return provider.query(
        query_string=query,
        start=start_iso,
        end=end_iso,
        step=step
    )
