"""
Workflow control tools for programmatically stopping workflow execution.
"""

import json
from typing import Dict, Any, Optional

_PR_WORKFLOW_ALLOWED = True
_PR_WORKFLOW_REASON = None

def check_incident_detection_result() -> Dict[str, Any]:
    """
    Programmatically check if incident was detected.
    This tool is called by WorkflowGuardAgent to check the IncidentDetectionAgent's output.
    
    Note: The agent should check conversation history for IncidentDetectionAgent's JSON output
    with "incident_detected" and "recommendation" fields.
    
    Returns:
        Dict with instructions for the agent to check
    """
    # This tool provides instructions - the actual check happens in the agent's logic
    # The agent should look for JSON with "incident_detected": false or "recommendation": "skip"
    return {
        "instruction": "Check conversation history for IncidentDetectionAgent's JSON output. Look for 'incident_detected': false or 'recommendation': 'skip' to determine if workflow should stop.",
        "check_for": ["incident_detected", "recommendation"],
        "stop_if": {
            "incident_detected": False,
            "recommendation": "skip"
        }
    }


def stop_workflow(reason: str = "No incident detected") -> Dict[str, Any]:
    """
    Programmatically mark workflow as stopped.
    This sets a global flag and returns a marker that indicates the workflow should not proceed.
    
    Args:
        reason: Reason for stopping the workflow
    
    Returns:
        Dict indicating workflow should stop
    """
    # Return a marker that agents can cite when stopping execution
    return {
        "reason": reason,
        "message": "SKIP: No incident detected. Workflow terminated.",
        "should_proceed": False
    }


def reset_pr_workflow_gate() -> Dict[str, Any]:
    """
    Reset the PR workflow gate so branch/file/PR agents know they can proceed unless blocked later.
    """
    global _PR_WORKFLOW_ALLOWED, _PR_WORKFLOW_REASON
    _PR_WORKFLOW_ALLOWED = True
    _PR_WORKFLOW_REASON = None
    return {
        "allowed": _PR_WORKFLOW_ALLOWED,
        "reason": _PR_WORKFLOW_REASON,
    }


def block_pr_workflow(reason: str = "No patch available") -> Dict[str, Any]:
    """
    Block the PR workflow for the current incident run.
    """
    global _PR_WORKFLOW_ALLOWED, _PR_WORKFLOW_REASON
    _PR_WORKFLOW_ALLOWED = False
    _PR_WORKFLOW_REASON = reason
    return {
        "allowed": _PR_WORKFLOW_ALLOWED,
        "reason": _PR_WORKFLOW_REASON,
    }


def check_pr_workflow_gate() -> Dict[str, Any]:
    """
    Return the current PR workflow gate status.
    """
    return {
        "allowed": _PR_WORKFLOW_ALLOWED,
        "reason": _PR_WORKFLOW_REASON,
    }

