import os
import httpx
import base64
from typing import List, Dict, Any, Optional
from tools.telemetry.base import TelemetryProvider

class PrometheusProvider(TelemetryProvider):
    """
    Telemetry provider for Prometheus.
    """

    def __init__(self):
        self.host = os.getenv("PROMETHEUS_HOST", "").strip().rstrip("/")
        self.basic_auth = os.getenv("PROMETHEUS_BASICAUTH", "").strip()
        
        # Fallback to Grafana host if Prometheus host is not set (often same instance)
        if not self.host and os.getenv("GRAFANA_HOST"):
             self.host = os.getenv("GRAFANA_HOST", "").strip().rstrip("/")

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.basic_auth:
            auth_b64 = base64.b64encode(self.basic_auth.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {auth_b64}"
        elif os.getenv("GRAFANA_BASICAUTH"):
             # Fallback auth
             auth = os.getenv("GRAFANA_BASICAUTH", "").strip()
             auth_b64 = base64.b64encode(auth.encode("utf-8")).decode("utf-8")
             headers["Authorization"] = f"Basic {auth_b64}"
        return headers

    def query(
        self,
        query_string: str,
        start: str,
        end: str,
        step: Optional[int] = 15
    ) -> List[Dict[str, Any]]:
        if not self.host:
            raise ValueError("PROMETHEUS_HOST environment variable is not set")

        url = f"{self.host}/api/v1/query_range"
        headers = self._get_headers()
        
        params = {
            "query": query_string.strip(),
            "start": start,
            "end": end,
            "step": step or 15
        }

        try:
            print(f"[PROMETHEUS] Querying: {query_string}")
            response = httpx.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if data.get("status") == "success":
                for result in data.get("data", {}).get("result", []):
                    metric = result.get("metric", {})
                    values = result.get("values", [])
                    
                    # Transform to a more friendly format for the LLM
                    results.append({
                        "metric": metric,
                        "values": values, # List of [timestamp, value]
                        "summary": {
                            "count": len(values),
                            "min": min([float(v[1]) for v in values]) if values else 0,
                            "max": max([float(v[1]) for v in values]) if values else 0,
                            "avg": sum([float(v[1]) for v in values]) / len(values) if values else 0
                        }
                    })
            return results

        except httpx.HTTPStatusError as e:
            error_msg = f"Prometheus query failed: {e.response.status_code} {e.response.reason_phrase}"
            try:
                error_body = e.response.json()
                if "error" in error_body:
                    error_msg += f" - {error_body['error']}"
            except:
                pass
            raise Exception(error_msg)
        except httpx.HTTPError as e:
            raise Exception(f"Prometheus connection failed: {str(e)}")
