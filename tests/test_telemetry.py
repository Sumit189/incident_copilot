import pytest
from unittest.mock import patch, MagicMock
from tools.telemetry_tool import fetch_telemetry
from tools.telemetry.factory import TelemetryFactory
from tools.telemetry.loki import LokiProvider
from tools.telemetry.prometheus import PrometheusProvider

@patch('tools.telemetry.loki.LokiProvider.query')
def test_fetch_telemetry_logs(mock_query):
    mock_query.return_value = [{"log": "error"}]
    
    result = fetch_telemetry(
        query_type="logs",
        query='{app="foo"}',
        lookup_window_seconds=60
    )
    
    mock_query.assert_called_once()
    assert result == [{"log": "error"}]

@patch('tools.telemetry.prometheus.PrometheusProvider.query')
def test_fetch_telemetry_metrics(mock_query):
    mock_query.return_value = [{"metric": {}, "values": []}]
    
    result = fetch_telemetry(
        query_type="metrics",
        query='up',
        lookup_window_seconds=60
    )
    
    mock_query.assert_called_once()
    assert result == [{"metric": {}, "values": []}]

def test_factory_defaults():
    assert isinstance(TelemetryFactory.get_logs_provider(), LokiProvider)
    assert isinstance(TelemetryFactory.get_metrics_provider(), PrometheusProvider)

@patch('os.getenv')
def test_factory_custom(mock_getenv):
    # Configure mock to return 'loki' when asked for logs provider
    def getenv_side_effect(key, default=None):
        if key == "TELEMETRY_PROVIDER_LOGS":
            return "loki"
        return default
    
    mock_getenv.side_effect = getenv_side_effect
    
    # Should return LokiProvider
    provider = TelemetryFactory.get_logs_provider()
    assert isinstance(provider, LokiProvider)
