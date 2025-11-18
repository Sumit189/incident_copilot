import pytest
from unittest.mock import patch, MagicMock
import requests
from tools.incident_actions import publish_incident_report

@patch('tools.post_process_helper.POST_PROCESS_URL', 'http://example.com/post')
@patch('tools.email_sender.get_on_call_engineers')
@patch('tools.email_helper.send_incident_email')
@patch('requests.post')
def test_publish_incident_report_success(mock_post, mock_send_email, mock_get_engineers):
    # Setup mocks
    mock_get_engineers.return_value = ["sre@example.com"]
    mock_send_email.return_value = {"status": "sent"}
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    # Execute
    result = publish_incident_report(
        email_subject="Test Subject",
        email_body="Test Body",
        incident_summary="Test Incident",
        root_cause="Test RCA",
        mitigation_suggestions="Test Suggestion",
        proposed_solution="Test Solution",
        pr_url="http://github.com/pr/1",
        pr_number=1
    )

    # Verify Email
    mock_send_email.assert_called_once()
    assert result["email_status"]["status"] == "sent"

    # Verify Post Process
    mock_post.assert_called_once_with(
        'http://example.com/post',
        json={
            "incident": "Test Incident",
            "rca": "Test RCA",
            "suggestion": "Test Suggestion",
            "solution": "Test Solution",
            "pr": "http://github.com/pr/1"
        },
        timeout=10
    )
    assert result["post_process_status"]["status"] == "success"

@patch('tools.post_process_helper.POST_PROCESS_URL', '')
@patch('tools.email_sender.get_on_call_engineers')
@patch('tools.email_helper.send_incident_email')
def test_publish_incident_report_skip_post_process(mock_send_email, mock_get_engineers):
    # Setup mocks
    mock_get_engineers.return_value = ["sre@example.com"]
    mock_send_email.return_value = {"status": "sent"}

    # Execute
    result = publish_incident_report(
        email_subject="Test Subject",
        email_body="Test Body",
        incident_summary="Test Incident",
        root_cause="Test RCA",
        mitigation_suggestions="Test Suggestion",
        proposed_solution="Test Solution"
    )

    # Verify
    assert result["email_status"]["status"] == "sent"
    assert result["post_process_status"]["status"] == "skipped"

@patch('tools.post_process_helper.POST_PROCESS_URL', 'http://example.com/post')
@patch('tools.email_sender.get_on_call_engineers')
@patch('tools.email_helper.send_incident_email')
@patch('requests.post')
def test_publish_incident_report_partial_failure(mock_post, mock_send_email, mock_get_engineers):
    # Setup mocks: Email fails, Post-process succeeds
    mock_get_engineers.side_effect = Exception("Email Service Down")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    # Execute
    result = publish_incident_report(
        email_subject="Test Subject",
        email_body="Test Body",
        incident_summary="Test Incident",
        root_cause="Test RCA",
        mitigation_suggestions="Test Suggestion",
        proposed_solution="Test Solution"
    )

    # Verify
    assert result["email_status"]["status"] == "failed"
    assert "Email Service Down" in result["email_status"]["error"]
    
    assert result["post_process_status"]["status"] == "success"
    mock_post.assert_called_once()
