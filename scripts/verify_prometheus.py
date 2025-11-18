import os
import sys
import time
import subprocess
import threading

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.telemetry.prometheus import PrometheusProvider

def stream_reader(pipe, prefix):
    try:
        for line in iter(pipe.readline, b''):
            print(f"{prefix}: {line.decode('utf-8').strip()}")
    except Exception:
        pass

def test_provider():
    # Set env var to point to mock
    os.environ["PROMETHEUS_HOST"] = "http://localhost:9090"
    
    print("Waiting for mock server...")
    time.sleep(2)
    
    try:
        provider = PrometheusProvider()
        print("Querying mock Prometheus for CPU...")
        results = provider.query(
            query_string="process_cpu_seconds_total",
            start="2023-01-01T00:00:00Z", # Mock ignores time
            end="2023-01-01T01:00:00Z"
        )
        
        print(f"Success! Received {len(results)} results.")
        if results:
            print("Sample result:", results[0])
            # Verify value is in high range (90-99)
            val = float(results[0]['values'][0][1])
            print(f"Returned value: {val}")
            if val > 89.0:
                print("VERIFICATION PASSED: Value is HIGH (>89)")
            else:
                print("VERIFICATION FAILED: Value is NOT high")
        
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    # Prepare environment for the server
    server_env = os.environ.copy()
    server_env["MOCK_CPU"] = "high"
    
    # Start mock server in background with the custom environment
    server_process = subprocess.Popen(
        [sys.executable, "scripts/mock_prometheus.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=server_env
    )
    
    # Start threads to read server output
    t_out = threading.Thread(target=stream_reader, args=(server_process.stdout, "[SERVER OUT]"))
    t_err = threading.Thread(target=stream_reader, args=(server_process.stderr, "[SERVER ERR]"))
    t_out.daemon = True
    t_err.daemon = True
    t_out.start()
    t_err.start()
    
    try:
        test_provider()
    finally:
        print("Terminating server...")
        server_process.terminate()
        server_process.wait()
