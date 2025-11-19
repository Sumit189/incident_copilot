import pytest
from unittest.mock import MagicMock, patch
import base64
import agents.github

@pytest.fixture
def mock_httpx_client():
    with patch("agents.github.httpx.Client") as mock_client:
        yield mock_client

@pytest.fixture
def mock_env_vars(monkeypatch):
    # Clear cache
    agents.github._OWNER_REPO_CACHE = None
    agents.github._OWNER_REPO_SOURCE = None
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setattr(agents.github, "GITHUB_TOKEN", "fake_token")

def test_apply_change_to_file_success(mock_httpx_client, mock_env_vars):
    # Mock GET response (current content)
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    original_content = "line1\nline2\nline3"
    encoded_content = base64.b64encode(original_content.encode("utf-8")).decode("utf-8")
    mock_get_resp.json.return_value = {
        "content": encoded_content,
        "encoding": "base64",
        "sha": "old_sha"
    }
    
    # Mock PUT response (update success)
    mock_put_resp = MagicMock()
    mock_put_resp.status_code = 200
    mock_put_resp.json.return_value = {"commit": {"sha": "new_sha"}}
    
    # Setup client mock
    client_instance = mock_httpx_client.return_value.__enter__.return_value
    client_instance.get.return_value = mock_get_resp
    client_instance.put.return_value = mock_put_resp
    
    # Call function
    result = agents.github.apply_change_to_file(
        path="test.py",
        search_content="line2",
        replace_content="line2_modified",
        branch="feature-branch"
    )
    
    # Assertions
    if result["status"] != "success":
        print(f"DEBUG: Result: {result}")
    
    assert result["status"] == "success"
    assert result["message"] == "Successfully updated test.py"
    
    # Verify PUT payload
    call_args = client_instance.put.call_args
    payload = call_args.kwargs["json"]
    decoded_new_content = base64.b64decode(payload["content"]).decode("utf-8")
    assert decoded_new_content == "line1\nline2_modified\nline3"
    assert payload["sha"] == "old_sha"

def test_apply_change_to_file_search_not_found(mock_httpx_client, mock_env_vars):
    # Mock GET response
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    original_content = "line1\nline2\nline3"
    encoded_content = base64.b64encode(original_content.encode("utf-8")).decode("utf-8")
    mock_get_resp.json.return_value = {
        "content": encoded_content,
        "encoding": "base64",
        "sha": "old_sha"
    }
    
    client_instance = mock_httpx_client.return_value.__enter__.return_value
    client_instance.get.return_value = mock_get_resp
    
    # Call function with non-existent search content
    result = agents.github.apply_change_to_file(
        path="test.py",
        search_content="missing_line",
        replace_content="whatever",
        branch="feature-branch"
    )
    
    if result["status"] != "error":
         print(f"DEBUG: Result: {result}")

    assert result["status"] == "error"
    assert "Search content not found" in result["message"]

def test_apply_change_to_file_fuzzy_match(mock_httpx_client, mock_env_vars):
    # Mock GET response
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    original_content = "  line2  "
    encoded_content = base64.b64encode(original_content.encode("utf-8")).decode("utf-8")
    mock_get_resp.json.return_value = {
        "content": encoded_content,
        "encoding": "base64",
        "sha": "old_sha"
    }
    
    # Mock PUT response
    mock_put_resp = MagicMock()
    mock_put_resp.status_code = 200
    mock_put_resp.json.return_value = {"commit": {"sha": "new_sha"}}
    
    client_instance = mock_httpx_client.return_value.__enter__.return_value
    client_instance.get.return_value = mock_get_resp
    client_instance.put.return_value = mock_put_resp
    
    # Call function with whitespace mismatch
    result = agents.github.apply_change_to_file(
        path="test.py",
        search_content="line2", # No whitespace
        replace_content="line2_modified",
        branch="feature-branch"
    )
    
    if result["status"] != "success":
        print(f"DEBUG: Result: {result}")
    
    assert result["status"] == "success"
    
    call_args = client_instance.put.call_args
    payload = call_args.kwargs["json"]
    decoded_new_content = base64.b64decode(payload["content"]).decode("utf-8")
    assert decoded_new_content == "  line2_modified  "
