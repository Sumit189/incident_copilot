import json
import re
from typing import List, Dict, Any, Optional, Tuple
from tools.telemetry.base import TelemetryProvider

class MockLokiProvider(TelemetryProvider):
    def __init__(self, scenario_data: Dict[str, Any]):
        self.logs = scenario_data.get("logs", [])

    def _parse_logql_query(self, query_string: str) -> Tuple[Optional[str], List[str], List[str]]:

        service_match = re.search(r'service_name\s*=\s*"([^"]+)"', query_string)
        service_name = service_match.group(1) if service_match else None
        

        level_match = re.search(r'level\s*=~\s*"([^"]+)"', query_string)
        level_options = []
        if level_match:
            level_pattern = level_match.group(1)
            level_options = [l.strip().lower() for l in level_pattern.split("|")]
        

        text_filters = re.findall(r'\|=\s*"([^"]+)"', query_string)
        
        return service_name, level_options, text_filters

    def _format_log_entry(self, log_entry: Dict[str, Any], service_name: Optional[str]) -> Dict[str, Any]:
        log_text = log_entry.get("log", "")
        parsed_log = log_entry.get("parsed", {})
        log_level = parsed_log.get("level", "").lower()
        
        stream_labels = {}
        if service_name:
            stream_labels["service_name"] = service_name
        if log_level:
            stream_labels["level"] = log_level
        
        return {
            "timestamp": log_entry.get("timestamp", "0"),
            "log": log_text,
            "stream_labels": stream_labels,
            "level": parsed_log.get("level"),
            "message": parsed_log.get("message"),
            "parsed": parsed_log
        }

    def _matches_filters(self, log_entry: Dict[str, Any], level_options: List[str], text_filters: List[str]) -> bool:
        log_text = log_entry.get("log", "")
        parsed_log = log_entry.get("parsed", {})
        log_level = parsed_log.get("level", "").lower()
        
        if level_options and (not log_level or log_level not in level_options):
            return False
        
        if text_filters:
            log_text_lower = log_text.lower()
            if not all(tf.lower() in log_text_lower for tf in text_filters):
                return False
        
        return True

    def query(
        self,
        query_string: str,
        start: str,
        end: str,
        step: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        print(f"[MOCK LOKI] Query: {query_string[:100]}")
        
        service_name, level_options, text_filters = self._parse_logql_query(query_string)
        
        results = []
        for entry in self.logs:
            if self._matches_filters(entry, level_options, text_filters):
                results.append(self._format_log_entry(entry, service_name))
        
        print(f"[MOCK LOKI] Returning {len(results)} matching logs")
        return results

class MockPrometheusProvider(TelemetryProvider):
    def __init__(self, scenario_data: Dict[str, Any]):
        self.metrics = scenario_data.get("metrics", {})

    def query(
        self,
        query_string: str,
        start: str,
        end: str,
        step: Optional[int] = 15
    ) -> List[Dict[str, Any]]:
        print(f"[MOCK PROMETHEUS] Query: {query_string[:100]}")
        

        metric_name_match = re.match(r'^([a-zA-Z0-9_:]+)', query_string)
        if not metric_name_match:

             for key, data in self.metrics.items():
                if key in query_string:
                    print(f"[MOCK PROMETHEUS] Loose matched metric: {key}, returning {len(data)} series")
                    return data
             print(f"[MOCK PROMETHEUS] No matching metric found")
             return []

        metric_name = metric_name_match.group(1)
        
        if metric_name in self.metrics:
            data = self.metrics[metric_name]
            print(f"[MOCK PROMETHEUS] Exact matched metric: {metric_name}, returning {len(data)} series")
            return data
            
        print(f"[MOCK PROMETHEUS] Metric '{metric_name}' not found in scenario metrics")
        return []

class MockGitHubClient:
    def __init__(self, scenario_data: Dict[str, Any]):
        self.files = scenario_data.get("files", {})
        self.prs = []
        self.branches = ["main"]
        self.commits = []

    def get_file_content(self, path: str, ref: str) -> str:
        return self.files.get(path, "")

    def create_branch(self, branch_name: str, base_branch: str) -> Dict[str, Any]:
        if branch_name in self.branches:
            return {"status": "error", "message": "Branch already exists"}
        self.branches.append(branch_name)
        return {"status": "success", "branch_name": branch_name}

    def update_file(self, path: str, content: str, branch: str, message: str) -> Dict[str, Any]:
        self.files[path] = content
        self.commits.append({"message": message, "branch": branch, "path": path})
        return {
            "status": "success",
            "path": path,
            "branch": branch,
            "commit_sha": "mock-sha",
            "message": f"Updated {path}"
        }

    def create_pr(self, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        pr_number = len(self.prs) + 1
        pr = {
            "number": pr_number,
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "html_url": f"https://github.com/mock/repo/pull/{pr_number}"
        }
        self.prs.append(pr)
        return {
            "status": "success",
            "pr_number": pr_number,
            "pr_url": pr["html_url"],
            "branch": head,
            "base": base,
            "message": title,
            "merged": False
        }
