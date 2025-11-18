import os
from tools.telemetry.base import TelemetryProvider
from tools.telemetry.loki import LokiProvider
from tools.telemetry.prometheus import PrometheusProvider

class TelemetryFactory:
    @staticmethod
    def get_logs_provider() -> TelemetryProvider:
        provider_type = os.getenv("TELEMETRY_PROVIDER_LOGS", "loki").lower()
        
        if provider_type == "loki":
            return LokiProvider()
        else:
            raise ValueError(f"Unknown logs provider: {provider_type}")

    @staticmethod
    def get_metrics_provider() -> TelemetryProvider:
        provider_type = os.getenv("TELEMETRY_PROVIDER_METRICS", "prometheus").lower()
        
        if provider_type == "prometheus":
            return PrometheusProvider()
        else:
            raise ValueError(f"Unknown metrics provider: {provider_type}")
