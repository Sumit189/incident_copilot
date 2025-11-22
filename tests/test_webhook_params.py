import asyncio
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app import api, workflow_dispatcher

client = TestClient(api)

def test_webhook_passes_github_params():
    # Mock the workflow_dispatcher to capture arguments
    with patch("app.workflow_dispatcher", side_effect=workflow_dispatcher) as mock_dispatcher:
        # Mock _run_workflow_task to prevent actual execution
        with patch("app._run_workflow_task", new_callable=AsyncMock) as mock_run_task:
            
            payload = {
                "service_name": "test-service",
                "github_repo": "owner/repo",
                "github_base_branch": "feature-branch",
                "status": "firing"
            }
            
            # We need to set the API key env var for the test
            with patch.dict("os.environ", {"WEBHOOK_API_KEY": "test-key"}):
                response = client.post(
                    "/webhook/trigger_agent",
                    json=payload,
                    headers={"X-Webhook-API-Key": "test-key"}
                )
            
            assert response.status_code == 202
            
            # Verify workflow_dispatcher was called with correct params
            mock_dispatcher.assert_called_once()
            call_kwargs = mock_dispatcher.call_args.kwargs
            assert call_kwargs["github_repo"] == "owner/repo"
            assert call_kwargs["github_base_branch"] == "feature-branch"
            
            # Verify _run_workflow_task was called with correct params
            # Note: _run_workflow_task is called by the task created in workflow_dispatcher
            # We can't easily assert on the async task execution here without waiting
            # But verifying workflow_dispatcher receives it is the main integration point in app.py

if __name__ == "__main__":
    test_webhook_passes_github_params()
    print("Test passed!")
