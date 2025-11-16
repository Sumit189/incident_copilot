# tools/email_sender.py

import os
import json
import base64
from typing import List, Optional

# Gmail API credentials (populated dynamically from the environment)
GMAIL_CLIENT_ID = ""
GMAIL_CLIENT_SECRET = ""
GMAIL_REFRESH_TOKEN = ""
GMAIL_USER_EMAIL = ""

ON_CALL_ENGINEERS_JSON = os.getenv("ON_CALL_ENGINEERS", '["sumit.18.paul@gmail.com"]')


def _load_env_from_process() -> None:
    """Refresh Gmail credential values from environment variables."""
    global GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_USER_EMAIL

    GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
    GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
    GMAIL_USER_EMAIL = os.getenv("GMAIL_USER_EMAIL", "")


_load_env_from_process()

# Gmail API service (initialized lazily)
_gmail_service = None


def get_on_call_engineers() -> List[str]:
    """Get the list of on-call engineer email addresses from environment variable."""
    import json
    try:
        engineers = json.loads(ON_CALL_ENGINEERS_JSON)
        if isinstance(engineers, list):
            return engineers
        return []
    except (json.JSONDecodeError, TypeError):
        return ["sumit.18.paul@gmail.com"]


def _initialize_gmail_api():
    """Initialize Gmail API service using OAuth2 credentials."""
    global _gmail_service

    _load_env_from_process()
    
    if _gmail_service is not None:
        return _gmail_service
    
    print(f"[EMAIL SENDER] Initializing Gmail API...")
    
    if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN]):
        error_msg = "Gmail API configuration missing: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, or GMAIL_REFRESH_TOKEN not set"
        print(f"[EMAIL SENDER] ERROR: {error_msg}")
        raise ValueError(error_msg)
    
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import httpx
        
        # Try direct HTTP refresh first (matching Node.js approach)
        print(f"[EMAIL SENDER] Refreshing OAuth token...")
        print(f"[EMAIL SENDER] Client ID: {GMAIL_CLIENT_ID[:20]}...")
        print(f"[EMAIL SENDER] Refresh token: {GMAIL_REFRESH_TOKEN[:20]}...")
        
        # Try direct HTTP refresh (like Node.js does)
        try:
            token_response = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GMAIL_CLIENT_ID,
                    "client_secret": GMAIL_CLIENT_SECRET,
                    "refresh_token": GMAIL_REFRESH_TOKEN,
                    "grant_type": "refresh_token"
                },
                timeout=30.0
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            if access_token:
                print(f"[EMAIL SENDER] Token refreshed successfully via direct HTTP")
                # Create credentials with the access token
                creds = Credentials(
                    token=access_token,
                    refresh_token=GMAIL_REFRESH_TOKEN,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=GMAIL_CLIENT_ID,
                    client_secret=GMAIL_CLIENT_SECRET,
                    scopes=['https://www.googleapis.com/auth/gmail.send']
                )
            else:
                raise Exception("No access token in response")
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            print(f"[EMAIL SENDER] Direct HTTP refresh failed: {e.response.status_code}")
            try:
                error_json = e.response.json()
                print(f"[EMAIL SENDER] Error details: {error_json}")
            except:
                print(f"[EMAIL SENDER] Response: {error_body[:200]}")
            
            # Since the token works in Node.js, this might be an OAuth client configuration issue
            # Check: https://console.cloud.google.com/apis/credentials
            # - Verify OAuth client type (Web application vs Desktop app)
            # - Check redirect URIs configured
            # - Ensure Client ID/Secret match exactly
            error_msg = f"Token refresh failed: {e.response.status_code} - {error_body}"
            error_msg += "\n\nNOTE: If this token works in Node.js, check:"
            error_msg += "\n1. OAuth client type in Google Cloud Console"
            error_msg += "\n2. Redirect URIs configured for the OAuth client"
            error_msg += "\n3. Client ID/Secret match exactly between Node.js and Python"
            raise Exception(error_msg)
        except Exception as refresh_error:
            error_str = str(refresh_error)
            print(f"[EMAIL SENDER] ERROR: Token refresh failed: {error_str}")
            
            # Check if it's an invalid_grant error
            if 'invalid_grant' in error_str.lower():
                print(f"[EMAIL SENDER] The refresh token may be expired or invalid.")
                print(f"[EMAIL SENDER] Please generate a new refresh token using the OAuth2 flow.")
                print(f"[EMAIL SENDER] You can use: https://developers.google.com/gmail/api/quickstart/python")
            
            raise
        
        # Build Gmail API service (matching Node.js: google.gmail({ version: 'v1', auth: oauth2Client }))
        _gmail_service = build('gmail', 'v1', credentials=creds)
        print(f"[EMAIL SENDER] Gmail API initialized successfully")
        
        return _gmail_service
    except Exception as e:
        print(f"[EMAIL SENDER] ERROR: Failed to initialize Gmail API: {str(e)}")
        import traceback
        print(f"[EMAIL SENDER] Traceback: {traceback.format_exc()}")
        raise


def _create_email_message(to: List[str], subject: str, body: str, cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None, html_body: Optional[str] = None) -> str:
    """Create email message in RFC 2822 format and encode as base64url."""
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    # If HTML is provided, use multipart/alternative structure (HTML preferred)
    if html_body:
        msg = MIMEMultipart('alternative')
    else:
        msg = MIMEMultipart()
    
    msg["From"] = GMAIL_USER_EMAIL
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    
    # If HTML is provided, add both plain text (fallback) and HTML (preferred)
    if html_body:
        # Minimal plain text fallback (for email clients that don't support HTML)
        # Just a brief message - email clients will prefer the HTML version
        plain_text = "This is an HTML email. Please view in an HTML-capable email client to see the formatted content."
        msg.attach(MIMEText(plain_text, "plain"))
        
        # HTML version (primary - email clients will prefer this)
        msg.attach(MIMEText(html_body, "html"))
    else:
        # Only plain text if no HTML
        msg.attach(MIMEText(body, "plain"))
    
    # Add BCC recipients to the message (they won't appear in headers)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    
    # Convert to string and encode
    raw_message = msg.as_string()
    
    # Encode in base64url format (like Node.js code)
    encoded = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("utf-8")
    # Remove padding
    encoded = encoded.rstrip('=')
    
    return encoded


def send_email(
    to: List[str],
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    html_body: Optional[str] = None
) -> dict:
    """
    Send an email to the specified recipient(s) using Gmail API (preferred) or SMTP (fallback).
    _load_env_from_process()
    REQUIRED PARAMETERS:
    - to: A list of email addresses (REQUIRED). Example: ["user@example.com"] or ["user1@example.com", "user2@example.com"]
    - subject: The email subject line (REQUIRED). Example: "Incident Report"
    - body: The email body content as plain text (REQUIRED). Example: "This is the email body"
    
    OPTIONAL PARAMETERS:
    - cc: Optional list of CC recipients. Default: empty list. Example: ["cc@example.com"]
    - bcc: Optional list of BCC recipients. Default: empty list. Example: ["bcc@example.com"]

    IMPORTANT: The 'to' parameter MUST be a list, even for a single recipient.
    Correct: to=["user@example.com"]
    Wrong: to="user@example.com"

    Environment variables required for Gmail API:
    - GMAIL_CLIENT_ID: Gmail OAuth client ID
    - GMAIL_CLIENT_SECRET: Gmail OAuth client secret
    - GMAIL_REFRESH_TOKEN: Gmail OAuth refresh token
    - GMAIL_USER_EMAIL: Gmail user email address (used as From address)
    
    Returns:
        dict with status information:
        {
            "status": "sent" | "failed",
            "message_id": "<message_id>",
            "to": <list of recipients>,
            "subject": <subject>,
            "message": "<status message>"
        }
    """
    
    if cc is None:
        cc = []
    if bcc is None:
        bcc = []
    
    # Validate required parameters
    if not isinstance(to, list):
        raise TypeError(f"'to' parameter must be a list, got {type(to).__name__}. Example: ['user@example.com']")
    if not to:
        raise ValueError("'to' parameter cannot be empty. Provide at least one email address.")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("'subject' parameter is required and cannot be empty")
    if not isinstance(body, str):
        raise ValueError("'body' parameter is required and must be a string")
    
    print(f"\n[EMAIL SENDER] Starting email send process")
    print(f"[EMAIL SENDER] To: {to}")
    print(f"[EMAIL SENDER] Subject: {subject}")
    print(f"[EMAIL SENDER] Body length: {len(body)} characters")
    
    if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_USER_EMAIL]):
        error_msg = "Gmail API credentials (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_USER_EMAIL) must be set"
        print(f"[EMAIL SENDER] ERROR: {error_msg}")
        raise ValueError(error_msg)
    
    all_recipients = to + cc + bcc
    print(f"[EMAIL SENDER] All recipients: {all_recipients}")
    
    try:
        print(f"[EMAIL SENDER] Using Gmail API to send email...")
        gmail_service = _initialize_gmail_api()
        
        # Create email message
        email_message = _create_email_message(to, subject, body, cc, bcc, html_body)
        
        # Send via Gmail API
        print(f"[EMAIL SENDER] Sending email via Gmail API...")
        result = gmail_service.users().messages().send(
            userId='me',
            body={'raw': email_message}
        ).execute()
        
        message_id = result.get('id')
        print(f"[EMAIL SENDER] Email sent successfully via Gmail API!")
        print(f"[EMAIL SENDER] Message ID: {message_id}")
        
        return {
            "status": "sent",
            "message_id": message_id,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "message": f"Email sent successfully to {len(all_recipients)} recipient(s) via Gmail API"
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"[EMAIL SENDER] ERROR: Gmail API failed: {str(e)}")
        print(f"[EMAIL SENDER] Traceback:\n{error_details}")
        
        error_msg = f"Failed to send email via Gmail API: {str(e)}"
        if 'invalid_grant' in str(e).lower():
            error_msg += "\n\nTROUBLESHOOTING: The refresh token may be expired or invalid."
            error_msg += "\nTo fix this:"
            error_msg += "\n1. Generate a new refresh token using OAuth2 flow"
            error_msg += "\n2. Update GMAIL_REFRESH_TOKEN in your .env file"
        
        result = {
            "status": "failed",
            "message_id": None,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "message": error_msg
        }
        print(f"[EMAIL SENDER] Returning error result: {result}")
        return result

