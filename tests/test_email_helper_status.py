import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import email_helper


class EmailHelperStatusTests(unittest.TestCase):
    def setUp(self):
        email_helper.reset_email_status()

    @mock.patch("tools.email_helper._send_email")
    def test_records_successful_send(self, mock_send_email):
        mock_send_email.return_value = {
            "status": "sent",
            "message": "ok",
            "subject": "s",
        }

        result = email_helper.send_incident_email(
            to=["eng@example.com"],
            subject="Test",
            body="Body",
        )

        self.assertEqual(result["status"], "sent")
        self.assertTrue(email_helper.was_email_sent())
        status = email_helper.get_last_email_status()
        self.assertTrue(status["sent"])
        self.assertIsNotNone(status["timestamp"])
        self.assertEqual(status["result"], result)

    @mock.patch("tools.email_helper._send_email")
    def test_records_failed_send(self, mock_send_email):
        mock_send_email.return_value = {
            "status": "failed",
            "message": "smtp down",
            "subject": "s",
        }

        email_helper.reset_email_status()
        result = email_helper.send_incident_email(
            to=["eng@example.com"],
            subject="Test",
            body="Body",
        )

        self.assertEqual(result["status"], "failed")
        self.assertFalse(email_helper.was_email_sent())
        status = email_helper.get_last_email_status()
        self.assertFalse(status["sent"])
        self.assertEqual(status["result"], result)


if __name__ == "__main__":
    unittest.main()

