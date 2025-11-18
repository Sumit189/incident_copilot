import pytest
from unittest.mock import patch, MagicMock
from tools.email_helper import send_incident_email_to_oncall

@patch('tools.email_sender.get_on_call_engineers')
@patch('tools.email_helper.send_incident_email')
def test_send_incident_email_to_oncall_success(mock_send, mock_get_engineers):
    mock_get_engineers.return_value = ["sre@example.com"]
    mock_send.return_value = {"status": "sent"}
    
    result = send_incident_email_to_oncall(
        subject="Test Incident",
        body="This is a test.",
        pr_url="http://github.com/pr/1",
        pr_number=1
    )
    
    mock_get_engineers.assert_called_once()
    mock_send.assert_called_once_with(
        to=["sre@example.com"],
        subject="Test Incident",
        body="This is a test.",
        pr_url="http://github.com/pr/1",
        pr_number=1
    )
    assert result["status"] == "sent"
    assert result["recipients"] == ["sre@example.com"]

@patch('tools.email_sender.get_on_call_engineers')
def test_send_incident_email_to_oncall_no_recipients(mock_get_engineers):
    mock_get_engineers.return_value = []
    
    result = send_incident_email_to_oncall(
        subject="Test Incident",
        body="This is a test."
    )
    
    mock_get_engineers.assert_called_once()
    assert result["status"] == "failed"
    assert result["error"] == "No on-call engineers found"
