import os
import json
import httpx
import base64
from typing import List, Dict, Any, Optional
from incident_copilot.config import SERVICE_NAME

def _get_grafana_host() -> str:
    host = os.getenv("GRAFANA_HOST", "").strip()
    if not host:
        raise ValueError("GRAFANA_HOST environment variable is not set")
    return host.rstrip("/")


def _get_auth_headers() -> dict:
    """Get HTTP headers with Basic Auth for Grafana."""
    headers = {"Content-Type": "application/json"}
    grafana_basic_auth = os.getenv("GRAFANA_BASICAUTH", "").strip()
    if grafana_basic_auth:
        auth_b64 = base64.b64encode(grafana_basic_auth.encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {auth_b64}"
    return headers


def query_loki(log_query: str, start: str, end: str) -> List[Dict]:
    """
    Query Grafana Loki for logs matching `log_query` between `start` and `end` (ISO timestamps).
    Returns list of log entries (dicts).

    Args:
        log_query: Loki query string (LogQL query, e.g., '{job="orders-service"} |= "ERROR"')
        start: Start time (ISO format, e.g., "2025-11-14T00:00:00Z")
        end: End time (ISO format, e.g., "2025-11-15T00:00:00Z")

    Returns:
        List of dicts each with keys: `timestamp`, `log`, `stream_labels`.
    """
    if not log_query or not log_query.strip():
        raise ValueError("log_query cannot be empty. Please provide a valid Loki query (LogQL), e.g., '{job=\"orders-service\"} |= \"ERROR\"'")
    
    if log_query.strip() in ['{}', '{{}}', '']:
        raise ValueError(f"Invalid query: '{log_query}'. Please provide a valid Loki query (LogQL). Example: '{{job=\"orders-service\"}} |= \"ERROR\"'")
    
    grafana_host = _get_grafana_host()
    url = f"{grafana_host}/loki/api/v1/query_range"
    headers = _get_auth_headers()
    
    params = {
        "query": log_query.strip(),
        "start": start,
        "end": end,
        "limit": 1000
    }
    
    try:
        print(f"[LOKI] Querying: {log_query}")
        print(f"[LOKI] Time range: {start} to {end}")
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        
        entries = []
        for stream in data.get("data", {}).get("result", []):
            stream_labels = stream.get("stream", {})
            
            for entry in stream.get("values", []):
                log_text = entry[1]
                parsed_log = _parse_log_entry(log_text)
                
                entries.append({
                    "timestamp": entry[0],
                    "log": log_text,
                    "stream_labels": stream_labels,
                    "level": parsed_log.get("level"),
                    "message": parsed_log.get("message"),
                    "parsed": parsed_log
                })
        
        return entries
    except httpx.HTTPStatusError as e:
        error_msg = f"Failed to query Grafana Loki: {e.response.status_code} {e.response.reason_phrase}"
        try:
            error_body = e.response.json()
            if "message" in error_body:
                error_msg += f" - {error_body['message']}"
            if "error" in error_body:
                error_msg += f" - {error_body['error']}"
        except:
            error_msg += f" - {str(e)}"
        error_msg += f"\nQuery used: {log_query}"
        error_msg += f"\nURL: {url}?query={log_query.strip()}&start={start}&end={end}"
        raise Exception(error_msg)
    except httpx.HTTPError as e:
        raise Exception(f"Failed to query Grafana Loki: {str(e)}")


def _parse_log_entry(log_text: str) -> Dict[str, Any]:
    """
    Parse a log entry that may be in JSON format.
    Returns a dict with parsed fields, or empty dict if not JSON.
    
    Expected format: {"level": "info", "message": "..."}
    """
    if not log_text or not log_text.strip():
        return {}
    
    log_text = log_text.strip()
    
    if log_text.startswith("{") and log_text.endswith("}"):
        try:
            parsed = json.loads(log_text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    
    return {"raw": log_text}


