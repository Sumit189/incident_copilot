from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class TelemetryProvider(ABC):
    """
    Abstract base class for telemetry providers (logs, metrics, traces).
    """

    @abstractmethod
    def query(
        self,
        query_string: str,
        start: str,
        end: str,
        step: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a query against the telemetry provider.

        Args:
            query_string: The query string (e.g., LogQL for Loki, PromQL for Prometheus).
            start: Start time in ISO 8601 format.
            end: End time in ISO 8601 format.
            step: Optional step size in seconds (mostly for metrics).

        Returns:
            A list of dictionaries representing the results.
            Structure depends on the provider but should be JSON-serializable.
        """
        pass
