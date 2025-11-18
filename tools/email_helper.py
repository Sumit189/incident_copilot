from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from tools.email_sender import send_email as _send_email
from tools.email_html_formatter import format_incident_email_html
import re

_LAST_EMAIL_STATUS: Dict[str, Any] = {
    "sent": False,
    "timestamp": None,
    "result": None,
}


def reset_email_status() -> None:
    """Reset cached email delivery state."""
    global _LAST_EMAIL_STATUS
    _LAST_EMAIL_STATUS = {
        "sent": False,
        "timestamp": None,
        "result": None,
    }


def _record_email_status(result: Dict[str, Any]) -> None:
    """Persist the delivery result for verification/fallback logic."""
    global _LAST_EMAIL_STATUS
    _LAST_EMAIL_STATUS = {
        "sent": result.get("status") == "sent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }


def was_email_sent() -> bool:
    """Return True if the last email attempt succeeded."""
    return bool(_LAST_EMAIL_STATUS.get("sent"))


def get_last_email_status() -> Dict[str, Any]:
    """Expose the cached delivery metadata for reporting."""
    return _LAST_EMAIL_STATUS


def send_incident_email(
    to: List[str],
    subject: str,
    body: str,
    pr_url: Optional[str] = None,
    pr_number: Optional[int] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None
) -> dict:
    """
    Send an incident report email with automatic HTML formatting.
    
    Args:
        to: List of recipient email addresses
        subject: Email subject
        body: Plain text email body
        pr_url: Optional PR URL to include in email
        pr_number: Optional PR number
        cc: Optional CC recipients
        bcc: Optional BCC recipients
    
    Returns:
        Dict with send status
    """
    # Extract PR info from body if not provided
    if not pr_url:
        pr_url_match = re.search(r'https?://[^\s]+', body)
        if pr_url_match:
            pr_url = pr_url_match.group(0)
    
    if not pr_number and pr_url:
        pr_num_match = re.search(r'#(\d+)', body)
        if pr_num_match:
            try:
                pr_number = int(pr_num_match.group(1))
            except ValueError:
                pass
    
    # Generate HTML version
    html_body = format_incident_email_html(body, pr_url, pr_number)
    
    from agents.config import SAVE_OUTPUT
    if SAVE_OUTPUT:
        import os
        try:
            os.makedirs("output", exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            filename = f"output/email_{timestamp}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Subject: {subject}\n\n{body}")
            print(f"Saved email copy to {filename}")
        except Exception as e:
            print(f"Failed to save email copy: {e}")

    result = _send_email(
        to=to,
        subject=subject,
        body=body,
        html_body=html_body,
        cc=cc,
        bcc=bcc
    )
    _record_email_status(result)
    return result


def send_incident_email_to_oncall(
    subject: str,
    body: str,
    pr_url: Optional[str] = None,
    pr_number: Optional[int] = None
) -> dict:
    """
    Send an incident report email to all on-call engineers.
    
    Args:
        subject: Email subject
        body: Plain text email body
        pr_url: Optional PR URL to include in email
        pr_number: Optional PR number
    
    Returns:
        Dict with send status and recipient list
    """
    from tools.email_sender import get_on_call_engineers
    
    recipients = get_on_call_engineers()
    if not recipients:
        return {
            "status": "failed",
            "error": "No on-call engineers found",
            "recipients": []
        }
        
    result = send_incident_email(
        to=recipients,
        subject=subject,
        body=body,
        pr_url=pr_url,
        pr_number=pr_number
    )
    result["recipients"] = recipients
    return result

