import pytest
from unittest.mock import MagicMock, patch
from agents.github import apply_change_to_file, read_file_content
import base64

@pytest.fixture
def mock_github_env():
    with patch("agents.github.get_owner_repo", return_value=("owner", "repo")), \
         patch("agents.github.GITHUB_TOKEN", "token"):
        yield

def mock_response(content, encoding="base64"):
    resp = MagicMock()
    resp.status_code = 200
    if encoding == "base64":
        b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        resp.json.return_value = {"content": b64_content, "encoding": "base64", "sha": "sha"}
    else:
        resp.json.return_value = {"content": content, "encoding": encoding}
    return resp

def test_apply_change_exact_match(mock_github_env):
    with patch("httpx.Client") as MockClient:
        client_instance = MockClient.return_value.__enter__.return_value
        
        original_content = "line1\nline2\nline3"
        client_instance.get.return_value = mock_response(original_content)
        client_instance.put.return_value.status_code = 200
        client_instance.put.return_value.json.return_value = {"commit": {"sha": "new_sha"}}
        
        result = apply_change_to_file("file.txt", "line2", "line2_modified", "main")
        
        assert result["status"] == "success"
        # Verify put payload
        call_args = client_instance.put.call_args
        payload = call_args[1]["json"]
        decoded_new_content = base64.b64decode(payload["content"]).decode("utf-8")
        assert decoded_new_content == "line1\nline2_modified\nline3"

def test_apply_change_whitespace_mismatch(mock_github_env):
    with patch("httpx.Client") as MockClient:
        client_instance = MockClient.return_value.__enter__.return_value
        
        # File has indentation
        original_content = "def foo():\n    print('hello')\n    return True"
        client_instance.get.return_value = mock_response(original_content)
        client_instance.put.return_value.status_code = 200
        client_instance.put.return_value.json.return_value = {"commit": {"sha": "new_sha"}}
        
        # Search query has NO indentation (common LLM mistake)
        search_content = "print('hello')\nreturn True"
        replace_content = "print('world')\nreturn False"
        
        result = apply_change_to_file("file.py", search_content, replace_content, "main")
        
        assert result["status"] == "success"
        
        call_args = client_instance.put.call_args
        payload = call_args[1]["json"]
        decoded_new_content = base64.b64decode(payload["content"]).decode("utf-8")
        
        # Should preserve original indentation
        expected_content = "def foo():\n    print('world')\n    return False"
        assert decoded_new_content == expected_content

def test_apply_change_not_found(mock_github_env):
    with patch("httpx.Client") as MockClient:
        client_instance = MockClient.return_value.__enter__.return_value
        
        original_content = "line1\nline2"
        client_instance.get.return_value = mock_response(original_content)
        
        result = apply_change_to_file("file.txt", "nonexistent", "replace", "main")
        
        assert result["status"] == "error"
        assert "Search content not found" in result["message"]

def test_read_file_content_success(mock_github_env):
    with patch("httpx.Client") as MockClient:
        client_instance = MockClient.return_value.__enter__.return_value
        
        content = "file content"
        client_instance.get.return_value = mock_response(content)
        
        result = read_file_content("file.txt", "main")
        
        assert result == "file content"

def test_read_file_content_not_found(mock_github_env):
    with patch("httpx.Client") as MockClient:
        client_instance = MockClient.return_value.__enter__.return_value
        
        client_instance.get.return_value.status_code = 404
        
        result = read_file_content("file.txt", "main")
        
        assert result.startswith("Error: File 'file.txt' not found")
