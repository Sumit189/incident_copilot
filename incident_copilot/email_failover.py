from typing import Dict, List, Optional, Any
import json


def _extract_latest_json(agent_responses: Dict[str, List[str]], agent_name: str) -> Optional[Dict[str, Any]]:
    entries = agent_responses.get(agent_name) or []
    for entry in reversed(entries):
        try:
            return json.loads(entry)
        except (TypeError, json.JSONDecodeError):
            continue
    return None


def _format_list(values: Optional[List[str]]) -> str:
    cleaned = [v for v in (values or []) if v]
    return ", ".join(cleaned) if cleaned else "N/A"


def _build_action_plan(solution_data: Optional[Dict[str, Any]], suggestion_data: Optional[Dict[str, Any]]) -> str:
    steps: List[str] = []
    if solution_data:
        for solution in solution_data.get("solutions", []) or []:
            for step in solution.get("implementation_steps", []):
                if step:
                    steps.append(step)
        for mitigation in solution_data.get("mitigations", []) or []:
            for step in mitigation.get("steps", []):
                if step:
                    steps.append(step)
    if suggestion_data:
        for suggestion in suggestion_data.get("suggestions", []) or []:
            for step in suggestion.get("steps", []):
                if step:
                    steps.append(step)
    if not steps:
        return "No concrete steps supplied by the workflow. Continue investigating and keep logging new findings."
    numbered = [f"{idx}. {text}" for idx, text in enumerate(steps, start=1)]
    return "ACTION PLAN — " + " ".join(numbered)


def compose_incident_email(agent_responses: Dict[str, List[str]]) -> Optional[Dict[str, Any]]:
    detection = _extract_latest_json(agent_responses, "IncidentDetectionAgent")
    if not detection or not detection.get("incident_detected"):
        return None

    service = (detection.get("affected_services") or ["unknown-service"])[0]
    severity = detection.get("severity", "Unknown")
    time_window = detection.get("time_window") or {}
    start = time_window.get("start", "unknown")
    end = time_window.get("end", "unknown")
    symptoms = _format_list(detection.get("initial_symptoms"))
    error_summary = detection.get("error_summary") or {}
    total_errors = error_summary.get("total_errors", "unknown")
    error_types = _format_list(error_summary.get("error_types"))
    brief_issue = error_types if error_types != "N/A" else symptoms

    rca = _extract_latest_json(agent_responses, "RCAAgent")
    root_cause = (rca or {}).get("most_likely") or "RCA agent did not produce a summary."
    evidence = _format_list(((rca or {}).get("root_causes") or [{}])[0].get("evidence"))

    solution = _extract_latest_json(agent_responses, "SolutionGeneratorAgent")
    solution_message = (solution or {}).get("message") or "Solution generator did not produce a narrative summary."
    recommended_solution = (solution or {}).get("recommended_solution")
    if recommended_solution:
        solution_message = f"{solution_message} Recommended: {recommended_solution}."

    action_plan = _build_action_plan(solution, _extract_latest_json(agent_responses, "SuggestionAgent"))

    pr_data = _extract_latest_json(agent_responses, "PRCreatorAgent")
    pr_url = pr_data.get("pr_url") if pr_data else None
    pr_number = pr_data.get("pr_number") if pr_data else None
    if pr_url:
        pr_section = f"PULL REQUEST — Code changes are tracked in PR #{pr_number}: {pr_url}"
    else:
        pr_section = "PULL REQUEST — No pull request was opened yet."

    summary = (
        f"INCIDENT SUMMARY — Service: {service}, Severity: {severity}, "
        f"Time Window: {start} to {end}, Initial Symptoms: {symptoms}, Total Errors: {total_errors}, "
        f"Error Types: {error_types}."
    )
    root_cause_section = f"ROOT CAUSE — {root_cause} Evidence: {evidence}."
    solution_section = f"SOLUTION STATUS — {solution_message}"

    body = "\n\n".join([summary, root_cause_section, solution_section, action_plan, pr_section])
    subject = f"[INCIDENT] {service} - {severity} - {brief_issue}"

    return {
        "subject": subject,
        "body": body,
        "pr_url": pr_url,
        "pr_number": pr_number,
    }

