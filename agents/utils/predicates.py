import logging
from agents.utils.state import get_agent_snapshot

def _get_incident_payload(session):
    state = session.state

    payload = state.get("incident_status")
    if payload:
        return payload

    snapshot = get_agent_snapshot(session, "IncidentDetectionAgent") or {}
    if snapshot:
        state["incident_status"] = snapshot
        logging.info("[Predicates] Cached incident snapshot: %s", snapshot)
    return snapshot

def is_incident_confirmed(ctx) -> bool:
    """
    Predicate: incident_detected is True AND recommendation is not "skip"
    """
    payload = _get_incident_payload(ctx.session)
    if not isinstance(payload, dict):
        return False
        
    incident_detected = payload.get("incident_detected", False)
    recommendation = payload.get("recommendation", "proceed")
    return bool(incident_detected) and recommendation != "skip"

def is_code_issue(ctx) -> bool:
    """
    Predicate: incident_type_hint equals "code_issue"
    """
    snapshot = get_agent_snapshot(ctx.session, "IncidentDetectionAgent")
    if not isinstance(snapshot, dict):
        return False
        
    return snapshot.get("incident_type_hint") == "code_issue"

def is_patch_ready(ctx) -> bool:
    """
    Predicate: patch exists AND at least one file in patch.files_to_modify has proposed_code
    """
    solution = get_agent_snapshot(ctx.session, "SolutionGeneratorAgent")
    
    if not isinstance(solution, dict):
        return False
        
    patch = solution.get("patch")
    if not patch:
        return False
    files = patch.get("files_to_modify") or []
    for file_entry in files:
        if file_entry.get("proposed_code"):
            return True
    return False
