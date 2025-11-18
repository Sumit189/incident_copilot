from typing import Optional, Dict, Any
from tools.email_helper import send_incident_email_to_oncall
from tools.post_process_helper import trigger_post_process_action

def publish_incident_report(
    email_subject: str,
    email_body: str,
    incident_summary: str = "",
    root_cause: str = "",
    mitigation_suggestions: str = "",
    proposed_solution: str = "",
    pr_url: Optional[str] = None,
    pr_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Publishes the incident report by sending an email to on-call engineers
    and triggering any configured post-process actions.

    Args:
        email_subject: Subject line for the email.
        email_body: Body text of the email.
        incident_summary: Brief summary of the incident.
        root_cause: Root cause analysis.
        mitigation_suggestions: Suggestions for mitigation.
        proposed_solution: Proposed solution.
        pr_url: URL of the pull request (if any).
        pr_number: Number of the pull request (if any). Can be string or int.

    Returns:
        A dictionary containing the status of both the email and post-process actions.
    """
    import concurrent.futures
    import logging

    logger = logging.getLogger(__name__)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_email = executor.submit(
            send_incident_email_to_oncall,
            subject=email_subject,
            body=email_body,
            pr_url=pr_url,
            pr_number=int(pr_number) if pr_number and str(pr_number).isdigit() else None
        )
        future_post_process = executor.submit(
            trigger_post_process_action,
            incident=incident_summary,
            rca=root_cause,
            suggestion=mitigation_suggestions,
            solution=proposed_solution,
            pr=pr_url
        )

        try:
            email_result = future_email.result()
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            email_result = {"status": "failed", "error": str(e)}

        try:
            post_process_result = future_post_process.result()
        except Exception as e:
            logger.error(f"Post-process action failed: {e}")
            post_process_result = {"status": "failed", "error": str(e)}

    return {
        "email_status": email_result,
        "post_process_status": post_process_result
    }
