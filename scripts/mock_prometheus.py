import http.server
import socketserver
import json
import time
import urllib.parse
import random
import sys

PORT = 9090

class MockPrometheusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Log request for debugging
        print(f"[MOCK] Request: {self.path}", file=sys.stderr)
        
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path.rstrip("/")
        
        if path == "/api/v1/query_range":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            # Extract query param
            query_params = urllib.parse.parse_qs(parsed_path.query)
            query = query_params.get("query", [""])[0]
            
            print(f"[MOCK] Received query: {query}", file=sys.stderr)
            
            # Determine value based on query content and env vars
            import os
            
            def get_value_from_env(var_name, is_percentage=True):
                val = os.getenv(var_name, "").lower().strip()
                if not val:
                    return None
                
                if val == "high":
                    return random.uniform(90, 99) if is_percentage else random.uniform(100_000_000, 1_000_000_000) # 100MB - 1GB
                elif val == "mid":
                    return random.uniform(40, 60) if is_percentage else random.uniform(1_000_000, 10_000_000) # 1MB - 10MB
                elif val == "low":
                    return random.uniform(5, 15) if is_percentage else random.uniform(1_000, 100_000) # 1KB - 100KB
                
                try:
                    return float(val)
                except ValueError:
                    return None

            base_value = None
            
            if "cpu" in query.lower():
                base_value = get_value_from_env("MOCK_CPU", is_percentage=True)
                if base_value: print(f"[MOCK] Using configured CPU value: {base_value:.2f}", file=sys.stderr)
            elif "memory" in query.lower():
                base_value = get_value_from_env("MOCK_RAM", is_percentage=True)
                if base_value: print(f"[MOCK] Using configured RAM value: {base_value:.2f}", file=sys.stderr)
            elif "network" in query.lower() or "bytes" in query.lower():
                base_value = get_value_from_env("MOCK_NETWORK", is_percentage=False)
                if base_value: print(f"[MOCK] Using configured Network value: {base_value:.2f}", file=sys.stderr)
            
            # Generate mock data
            # Format: [timestamp, value]
            now = time.time()
            values = []
            for i in range(10):
                ts = now - (i * 60)
                
                if base_value is not None:
                    # Add slight jitter to configured value
                    val = str(base_value + random.uniform(-1, 1))
                else:
                    # Default to 0 for unknown metrics to avoid false positives
                    val = "0"
                
                values.append([ts, val])
            
            values.reverse()
            
            response = {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {
                                "__name__": "mock_metric",
                                "instance": "localhost:9090",
                                "job": "mock"
                            },
                            "values": values
                        }
                    ]
                }
            }
            
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            print(f"[MOCK] 404 Not Found for path: {path}", file=sys.stderr)
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        # Override to print to stderr so we can capture it
        sys.stderr.write("%s - - [%s] %s\n" %
                         (self.client_address[0],
                          self.log_date_time_string(),
                          format%args))

print(f"Starting Mock Prometheus on port {PORT}...", file=sys.stderr)

# Allow reuse address to avoid "Address already in use" during restarts
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("", PORT), MockPrometheusHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...", file=sys.stderr)
        httpd.server_close()
