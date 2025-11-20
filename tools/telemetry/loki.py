import os
import httpx
import base64
import json
from typing import List, Dict, Any, Optional
from tools.telemetry.base import TelemetryProvider

class LokiProvider(TelemetryProvider):
    """
    Telemetry provider for Grafana Loki.
    """

    def __init__(self):
        self.host = os.getenv("GRAFANA_HOST", "").strip().rstrip("/")
        self.basic_auth = os.getenv("GRAFANA_BASICAUTH", "").strip()
        
        if not self.host:
            # We don't raise here to allow instantiation, but query will fail if not set
            pass

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.basic_auth:
            auth_b64 = base64.b64encode(self.basic_auth.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {auth_b64}"
        return headers

    def _parse_log_entry(self, log_text: str) -> Dict[str, Any]:
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

    def query(
        self,
        query_string: str,
        start: str,
        end: str,
        step: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not self.host:
            raise ValueError("GRAFANA_HOST environment variable is not set")

        url = f"{self.host}/loki/api/v1/query_range"
        headers = self._get_headers()
        
        params = {
            "query": query_string.strip(),
            "start": start,
            "end": end,
            "limit": 1000
        }
        if step:
            params["step"] = step

        try:
            print(f"[LOKI] Querying: {query_string}")
            response = httpx.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            entries = []
            for stream in (data.get("data") or {}).get("result", []):
                stream_labels = stream.get("stream", {})
                
                for entry in stream.get("values", []):
                    # entry is [timestamp_ns, log_line]
                    log_text = entry[1]
                    parsed_log = self._parse_log_entry(log_text)
                    
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
            error_msg = f"Loki query failed: {e.response.status_code} {e.response.reason_phrase}"
            try:
                error_body = e.response.json()
                if "message" in error_body:
                    error_msg += f" - {error_body['message']}"
            except:
                pass
            raise Exception(error_msg)
        except httpx.HTTPError as e:
            raise Exception(f"Loki connection failed: {str(e)}")
