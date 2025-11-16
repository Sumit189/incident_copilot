import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from incident_copilot.email_failover import compose_incident_email


class EmailFailoverTests(unittest.TestCase):
    def test_compose_email_with_full_context(self):
        agent_responses = {
            "IncidentDetectionAgent": [json.dumps({
                "incident_detected": True,
                "severity": "High",
                "affected_services": ["issue-tester"],
                "time_window": {"start": "2025-11-16T00:00:00Z", "end": "2025-11-16T01:00:00Z"},
                "initial_symptoms": ["Validation error in /process endpoint"],
                "error_summary": {
                    "total_errors": 18,
                    "error_types": ["Validation error in /process endpoint"],
                },
            })],
            "RCAAgent": [json.dumps({
                "most_likely": "Code issue in /process validation",
                "root_causes": [{
                    "evidence": ["Repeated 'Validation error' stack traces"]
                }]
            })],
            "SolutionGeneratorAgent": [json.dumps({
                "message": "Solution agent response placeholder.",
                "recommended_solution": "Add input schema validation.",
                "solutions": [{
                    "implementation_steps": ["Add schema validator."],
                }],
                "mitigations": [{
                    "steps": ["Disable /process endpoint temporarily."]
                }]
            })],
            "SuggestionAgent": [json.dumps({
                "suggestions": [{
                    "steps": ["Alert stakeholders."]
                }]
            })],
            "PRCreatorAgent": [json.dumps({
                "status": "skipped",
                "pr_url": None,
                "pr_number": None
            })],
        }

        email_content = compose_incident_email(agent_responses)
        self.assertIsNotNone(email_content)
        self.assertIn("issue-tester", email_content["subject"])
        self.assertIn("INCIDENT SUMMARY", email_content["body"])
        self.assertIn("ROOT CAUSE", email_content["body"])
        self.assertIn("ACTION PLAN", email_content["body"])

    def test_returns_none_when_incident_not_detected(self):
        agent_responses = {
            "IncidentDetectionAgent": [json.dumps({
                "incident_detected": False
            })]
        }
        self.assertIsNone(compose_incident_email(agent_responses))


if __name__ == "__main__":
    unittest.main()

