import requests
import logging
from typing import Dict, Any, Optional
from agents.config import POST_PROCESS_URL

logger = logging.getLogger(__name__)

def trigger_post_process_action(
    incident: str,
    rca: str,
    suggestion: str,
    solution: str,
    pr: Optional[str] = None
) -> Dict[str, Any]:
    """
    Triggers a post-process action (e.g., webhook) with incident details.

    Args:
        incident: Summary of the incident.
        rca: Root cause analysis.
        suggestion: Suggestions for mitigation/prevention.
        solution: Proposed solution.
        pr: Pull request URL (optional).

    Returns:
        A dictionary indicating the status of the operation.
    """
    if not POST_PROCESS_URL:
        logger.info("POST_PROCESS_URL not set; skipping post-process action.")
        return {"status": "skipped", "reason": "POST_PROCESS_URL not configured"}

    payload = {
        "incident": incident,
        "rca": rca,
        "suggestion": suggestion,
        "solution": solution,
        "pr": pr
    }

    try:
        response = requests.post(POST_PROCESS_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Post-process action triggered successfully to {POST_PROCESS_URL}")
        return {"status": "success", "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to trigger post-process action: {e}")
        return {"status": "failed", "error": str(e)}
