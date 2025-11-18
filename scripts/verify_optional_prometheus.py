import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.telemetry.prometheus import PrometheusProvider

def test_optional_provider():
    # Ensure env var is unset
    if "PROMETHEUS_HOST" in os.environ:
        del os.environ["PROMETHEUS_HOST"]
    
    print("Testing PrometheusProvider with no host...")
    
    try:
        provider = PrometheusProvider()
        results = provider.query(
            query_string="up",
            start="2023-01-01T00:00:00Z",
            end="2023-01-01T01:00:00Z"
        )
        
        if results == []:
            print("SUCCESS: Returned empty list as expected.")
        else:
            print(f"FAILURE: Returned unexpected results: {results}")
            
    except Exception as e:
        print(f"FAILURE: Raised exception: {e}")

if __name__ == "__main__":
    test_optional_provider()
