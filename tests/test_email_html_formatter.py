import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv, dotenv_values

from tools.email_html_formatter import format_incident_email_html

ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)
_env_defaults = dotenv_values(dotenv_path=ENV_PATH)
for _key, _value in (_env_defaults or {}).items():
    if _key and _value and not os.getenv(_key):
        os.environ[_key] = _value

SAMPLE_EMAIL_BODY = """INCIDENT SUMMARY — Service: issue-tester, Severity: High, Time Window: 2025-11-16T00:00:00Z to 2025-11-17T00:00:00Z, Initial Symptoms: Error occurred, Invalid data, Validation error in /process endpoint, Total Errors: 18.

ROOT CAUSE — The 'issue-tester' service is experiencing a high severity incident indicated by multiple errors. The primary error identified is 'Validation error in /process endpoint', accompanied by 'Invalid data' and generic 'Error occurred' messages. This strongly suggests a code-related issue, likely within the data processing logic of the /process endpoint.

SOLUTION STATUS — The most recommended solution is to implement a 'patch' that addresses the data validation logic for the '/process' endpoint. While the Code Analyzer could not pinpoint specific files, the error messages 'Validation error in /process endpoint' and 'Invalid data' strongly suggest a code-level issue in how the application handles incoming data for this specific endpoint. Enhancing error handling is a secondary, but valuable, step to improve future debugging.

ACTION PLAN — 1. Review the code responsible for handling requests to the /process endpoint. 2. Identify the expected data schema or validation rules for the /process endpoint. 3. Modify the code to correctly validate and/or process the incoming data, or adjust the data being sent to the endpoint if it's being generated incorrectly. 4. Specifically, investigate why 'Invalid data' is being reported in conjunction with the validation error. 5. Enhance error handling in the /process endpoint to provide more specific error messages or stack traces for debugging. 6. Ensure all potential failure paths within the /process endpoint are caught and logged appropriately. 7. Temporarily disable the /process endpoint to prevent further errors and allow for investigation.

PULL REQUEST — Code changes for the validation fix are in PR #5: https://github.com/Sumit189/issue_test/pull/5"""


class EmailHtmlFormatterTests(unittest.TestCase):
    def test_structured_incident_email_rendering(self):
        pr_url = "https://github.com/Sumit189/issue_test/pull/5"
        html = format_incident_email_html(SAMPLE_EMAIL_BODY, pr_url=pr_url, pr_number=5)

        # Basic scaffolding
        self.assertIn("<title>Incident Report</title>", html)
        self.assertIn("Incident Summary", html)
        self.assertIn("Root Cause", html)
        self.assertIn("Solution Status", html)
        self.assertIn("Action Plan", html)

        # Summary table should include key fields
        self.assertIn("Service:", html)
        self.assertIn("issue-tester", html)
        self.assertIn("Severity:", html)
        self.assertIn("High", html)
        self.assertIn("Total Errors:", html)
        self.assertIn("18", html)

        # Root cause text should be preserved
        self.assertIn("Validation error in /process endpoint", html)

        # Action plan should render as an ordered list
        self.assertIn("<ol", html)
        self.assertIn("Temporarily disable the /process endpoint", html)

        # Pull request block should reference URL and number
        self.assertIn("CODE PATCH", html)
        self.assertIn("View PR #5", html)
        self.assertIn(pr_url, html)

if __name__ == "__main__":
    unittest.main()

