"""
Notification service for sending alerts via email and Slack.

This module provides functions to send alert notifications to configured channels.
Notifications are optional and failures should not block alert creation or resolution.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Email configuration
ALERT_EMAIL_ENABLED = os.getenv('ALERT_EMAIL_ENABLED', 'false').lower() == 'true'
ALERT_EMAIL_SMTP_HOST = os.getenv('ALERT_EMAIL_SMTP_HOST', '')
ALERT_EMAIL_SMTP_PORT = int(os.getenv('ALERT_EMAIL_SMTP_PORT', '587'))
ALERT_EMAIL_SMTP_USER = os.getenv('ALERT_EMAIL_SMTP_USER', '')
ALERT_EMAIL_SMTP_PASSWORD = os.getenv('ALERT_EMAIL_SMTP_PASSWORD', '')
ALERT_EMAIL_RECIPIENTS = os.getenv('ALERT_EMAIL_RECIPIENTS', '')
ALERT_EMAIL_FROM = os.getenv('ALERT_EMAIL_FROM', ALERT_EMAIL_SMTP_USER)
ALERT_EMAIL_USE_TLS = os.getenv('ALERT_EMAIL_USE_TLS', 'true').lower() == 'true'
ALERT_EMAIL_USE_SSL = os.getenv('ALERT_EMAIL_USE_SSL', 'false').lower() == 'true'

# Slack configuration
ALERT_SLACK_ENABLED = os.getenv('ALERT_SLACK_ENABLED', 'false').lower() == 'true'
ALERT_SLACK_WEBHOOK_URL = os.getenv('ALERT_SLACK_WEBHOOK_URL', '')
ALERT_SLACK_CHANNEL = os.getenv('ALERT_SLACK_CHANNEL', '#alerts')

# Try to import email libraries
try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.utils import formatdate
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    logger.warning("Email libraries not available")

# Try to import httpx for Slack webhooks
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available. Slack notifications will be disabled.")


# ============================================================================
# Helper Utilities (Private Functions)
# ============================================================================

def _validate_email_config() -> bool:
    """
    Validate that email configuration is complete and enabled.
    
    Returns:
        True if email is properly configured, False otherwise
    """
    if not ALERT_EMAIL_ENABLED:
        logger.debug("Email notifications are disabled")
        return False
    
    if not EMAIL_AVAILABLE:
        logger.warning("Email libraries not available")
        return False
    
    if not ALERT_EMAIL_SMTP_HOST or not ALERT_EMAIL_SMTP_USER or not ALERT_EMAIL_RECIPIENTS:
        logger.warning("Email configuration incomplete. Check ALERT_EMAIL_* environment variables.")
        return False
    
    return True


def _format_datetime(dt: Any) -> str:
    """
    Format datetime object or string to readable format.
    
    Args:
        dt: datetime object, string, or None
    
    Returns:
        Formatted datetime string
    """
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    elif isinstance(dt, str):
        return dt
    else:
        return str(dt) if dt else 'Unknown'


def _get_email_recipients() -> List[str]:
    """
    Parse and return list of email recipients.
    
    Returns:
        List of email addresses
    """
    if not ALERT_EMAIL_RECIPIENTS:
        return []
    
    return [email.strip() for email in ALERT_EMAIL_RECIPIENTS.split(',') if email.strip()]


# ============================================================================
# Email Content Formatters (Private Functions)
# ============================================================================

def _format_alert_creation_email(alert_data: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Format email content for alert creation notification.
    
    Args:
        alert_data: Dictionary containing alert data
    
    Returns:
        Tuple of (subject, plain_text_body, html_body)
    """
    alert_id = str(alert_data.get('alert_id', 'Unknown'))
    source = alert_data.get('source', 'Unknown')
    source_id = alert_data.get('source_id', 'Unknown')
    severity = alert_data.get('severity', 'Unknown')
    message = alert_data.get('message', 'No message')
    details = alert_data.get('details', {})
    created_at = _format_datetime(alert_data.get('created_at', 'Unknown'))
    
    # Format email subject
    subject = f"[{severity.upper()}] Alert from {source}: {source_id}"
    
    # Severity color mapping
    severity_colors = {
        'critical': '#FF0000',
        'warning': '#FFA500',
        'info': '#0066CC'
    }
    color = severity_colors.get(severity.lower(), '#808080')
    
    # Plain text body
    text_body = f"""Alert Notification

Alert ID: {alert_id}
Source: {source}
Source ID: {source_id}
Severity: {severity.upper()}
Message: {message}
Created At: {created_at}
"""
    
    # Only show details if it's a test alert (has "test": true in details)
    # Hide details in production to keep emails clean
    is_test_alert = details and isinstance(details, dict) and details.get('test') is True
    
    if details and is_test_alert:
        text_body += f"\nDetails:\n{json.dumps(details, indent=2)}"
    
    # HTML body
    html_body = f"""
    <html>
    <head></head>
    <body style="font-family: Arial, sans-serif;">
        <h2 style="color: {color};">Alert Notification - {severity.upper()}</h2>
        <table style="border-collapse: collapse; width: 100%;">
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Alert ID:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{alert_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Source:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{source}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Source ID:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{source_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Severity:</td>
                <td style="padding: 8px; border: 1px solid #ddd; color: {color}; font-weight: bold;">{severity.upper()}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Message:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{message}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Created At:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{created_at}</td>
            </tr>
        </table>
"""
    
    # Only show details section if it's a test alert
    if details and is_test_alert:
        details_json = json.dumps(details, indent=2)
        html_body += f"""
        <h3>Details:</h3>
        <pre style="background-color: #f5f5f5; padding: 10px; border: 1px solid #ddd; overflow-x: auto;">{details_json}</pre>
        """
    
    html_body += """
    </body>
    </html>
    """
    
    return subject, text_body, html_body


def _format_alert_resolution_email(alert_data: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Format email content for alert resolution notification.
    
    Args:
        alert_data: Dictionary containing resolved alert data
    
    Returns:
        Tuple of (subject, plain_text_body, html_body)
    """
    alert_id = str(alert_data.get('alert_id', 'Unknown'))
    source = alert_data.get('source', 'Unknown')
    source_id = alert_data.get('source_id', 'Unknown')
    severity = alert_data.get('severity', 'Unknown')
    message = alert_data.get('message', 'No message')
    resolved_at = _format_datetime(alert_data.get('resolved_at', 'Unknown'))
    resolved_by = alert_data.get('resolved_by', 'System')
    created_at = _format_datetime(alert_data.get('created_at', 'Unknown'))
    
    # Format email subject
    subject = f"[RESOLVED] Alert from {source}: {source_id} - {severity.upper()}"
    
    # Plain text body
    text_body = f"""Alert Resolved

Alert ID: {alert_id}
Source: {source}
Source ID: {source_id}
Severity: {severity.upper()}
Original Message: {message}
Created At: {created_at}
Resolved At: {resolved_at}
Resolved By: {resolved_by}

This alert has been marked as resolved.
"""
    
    # HTML body
    html_body = f"""
    <html>
    <head></head>
    <body style="font-family: Arial, sans-serif;">
        <h2 style="color: #28a745;">Alert Resolved ✓</h2>
        <table style="border-collapse: collapse; width: 100%;">
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Alert ID:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{alert_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Source:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{source}/{source_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Severity:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{severity.upper()}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Original Message:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{message}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Created At:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{created_at}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Resolved At:</td>
                <td style="padding: 8px; border: 1px solid #ddd; color: #28a745; font-weight: bold;">{resolved_at}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">Resolved By:</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{resolved_by}</td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return subject, text_body, html_body


# ============================================================================
# Core Email Sending Function (Private)
# ============================================================================

def _send_email(subject: str, text_body: str, html_body: str) -> bool:
    """
    Core function to send email via SMTP.
    
    This is the single point of email sending logic that handles SMTP connection,
    authentication, and sending. All email notifications use this function.
    
    Args:
        subject: Email subject line
        text_body: Plain text email body
        html_body: HTML email body
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    if not _validate_email_config():
        return False
    
    try:
        # Get recipients
        recipients = _get_email_recipients()
        if not recipients:
            logger.warning("No email recipients configured")
            return False
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['From'] = ALERT_EMAIL_FROM
        msg['To'] = ALERT_EMAIL_RECIPIENTS
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        
        # Add both plain text and HTML versions
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        if ALERT_EMAIL_USE_SSL:
            # Use SSL (port 465)
            server = smtplib.SMTP_SSL(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT)
        else:
            # Use TLS (port 587)
            server = smtplib.SMTP(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT)
            if ALERT_EMAIL_USE_TLS:
                server.starttls()
        
        server.login(ALERT_EMAIL_SMTP_USER, ALERT_EMAIL_SMTP_PASSWORD)
        server.sendmail(ALERT_EMAIL_FROM, recipients, msg.as_string())
        server.quit()
        
        logger.info(f"Email sent successfully: {subject}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {str(e)}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}", exc_info=True)
        return False


# ============================================================================
# Public Email Functions
# ============================================================================

def send_alert_creation_email(alert_data: Dict[str, Any]) -> bool:
    """
    Send an email notification when an alert is created.
    
    Args:
        alert_data: Dictionary containing alert data with keys:
            - alert_id: UUID
            - source: str
            - source_id: str
            - severity: str
            - message: str
            - details: dict (optional)
            - created_at: str or datetime
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        subject, text_body, html_body = _format_alert_creation_email(alert_data)
        return _send_email(subject, text_body, html_body)
    except Exception as e:
        logger.error(f"Error formatting or sending alert creation email: {str(e)}", exc_info=True)
        return False


def send_alert_resolution_email(alert_data: Dict[str, Any]) -> bool:
    """
    Send an email notification when an alert is resolved.
    
    Args:
        alert_data: Dictionary containing resolved alert data with keys:
            - alert_id: UUID
            - source: str
            - source_id: str
            - severity: str
            - message: str
            - created_at: str or datetime
            - resolved_at: str or datetime
            - resolved_by: str (optional)
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        subject, text_body, html_body = _format_alert_resolution_email(alert_data)
        return _send_email(subject, text_body, html_body)
    except Exception as e:
        logger.error(f"Error formatting or sending alert resolution email: {str(e)}", exc_info=True)
        return False


# ============================================================================
# Slack Notification Functions
# ============================================================================

def send_slack_notification(alert_data: Dict[str, Any]) -> bool:
    """
    Send an alert notification via Slack webhook.
    
    Args:
        alert_data: Dictionary containing alert data with keys:
            - alert_id: UUID
            - source: str
            - source_id: str
            - severity: str
            - message: str
            - details: dict (optional)
            - created_at: str or datetime
    
    Returns:
        True if Slack message was sent successfully, False otherwise
    """
    if not ALERT_SLACK_ENABLED:
        logger.debug("Slack notifications are disabled")
        return False
    
    if not HTTPX_AVAILABLE:
        logger.warning("httpx not available for Slack notifications")
        return False
    
    if not ALERT_SLACK_WEBHOOK_URL:
        logger.warning("Slack webhook URL not configured. Set ALERT_SLACK_WEBHOOK_URL environment variable.")
        return False
    
    try:
        # Prepare Slack message
        alert_id = str(alert_data.get('alert_id', 'Unknown'))
        source = alert_data.get('source', 'Unknown')
        source_id = alert_data.get('source_id', 'Unknown')
        severity = alert_data.get('severity', 'Unknown')
        message = alert_data.get('message', 'No message')
        details = alert_data.get('details', {})
        created_at = alert_data.get('created_at', 'Unknown')
        created_at_str = _format_datetime(created_at)
        
        # Determine color based on severity
        color_map = {
            'critical': '#FF0000',  # Red
            'warning': '#FFA500',   # Orange
            'info': '#0066CC',      # Blue
        }
        color = color_map.get(severity.lower(), '#808080')  # Gray default
        
        # Build Slack message payload
        slack_payload = {
            "channel": ALERT_SLACK_CHANNEL,
            "username": "Alert System",
            "icon_emoji": ":warning:",
            "attachments": [
                {
                    "color": color,
                    "title": f"Alert: {severity.upper()} - {source}/{source_id}",
                    "text": message,
                    "fields": [
                        {
                            "title": "Alert ID",
                            "value": str(alert_id),
                            "short": True
                        },
                        {
                            "title": "Source",
                            "value": f"{source}/{source_id}",
                            "short": True
                        },
                        {
                            "title": "Severity",
                            "value": severity.upper(),
                            "short": True
                        },
                        {
                            "title": "Created At",
                            "value": created_at_str,
                            "short": True
                        }
                    ],
                    "footer": "Alert System"
                }
            ]
        }
        
        # Add timestamp if created_at is a datetime object
        try:
            if isinstance(created_at, datetime):
                slack_payload["attachments"][0]["ts"] = int(created_at.timestamp())
            elif isinstance(created_at, str):
                # Try to parse ISO format timestamp
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    slack_payload["attachments"][0]["ts"] = int(dt.timestamp())
                except:
                    pass
        except:
            pass
        
        # Add details if available
        if details:
            details_text = json.dumps(details, indent=2)
            slack_payload["attachments"][0]["fields"].append({
                "title": "Details",
                "value": f"```{details_text}```",
                "short": False
            })
        
        # Send to Slack webhook
        import httpx as sync_httpx
        response = sync_httpx.post(
            ALERT_SLACK_WEBHOOK_URL,
            json=slack_payload,
            timeout=10.0
        )
        
        if response.status_code == 200:
            logger.info(f"Slack notification sent for alert {alert_id}")
            return True
        else:
            logger.warning(f"Slack webhook returned status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {str(e)}")
        return False


# ============================================================================
# Public Notification Wrappers
# ============================================================================

def send_alert_notification(alert_data: Dict[str, Any]) -> bool:
    """
    Send alert notifications via all configured channels when an alert is created.
    
    This function attempts to send notifications via email and Slack.
    It returns True if at least one notification was sent successfully.
    
    Args:
        alert_data: Dictionary containing alert data
    
    Returns:
        True if at least one notification was sent successfully, False otherwise
    """
    email_sent = False
    slack_sent = False
    
    # Try email
    if ALERT_EMAIL_ENABLED:
        try:
            email_sent = send_alert_creation_email(alert_data)
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
    
    # Try Slack
    if ALERT_SLACK_ENABLED:
        try:
            slack_sent = send_slack_notification(alert_data)
        except Exception as e:
            logger.error(f"Error sending Slack notification: {str(e)}")
    
    # Return True if at least one succeeded
    return email_sent or slack_sent


def send_alert_resolution_notification(alert_data: Dict[str, Any]) -> bool:
    """
    Send alert resolution notifications via all configured channels.
    
    This function attempts to send notifications via email and Slack when an alert is resolved.
    It returns True if at least one notification was sent successfully.
    
    Args:
        alert_data: Dictionary containing resolved alert data
    
    Returns:
        True if at least one notification was sent successfully, False otherwise
    """
    email_sent = False
    slack_sent = False
    
    # Try email
    if ALERT_EMAIL_ENABLED:
        try:
            email_sent = send_alert_resolution_email(alert_data)
        except Exception as e:
            logger.error(f"Error sending resolution email notification: {str(e)}")
    
    # Try Slack (optional - can add resolution Slack notification later if needed)
    # For now, we'll just send email for resolution
    
    # Return True if at least one succeeded
    return email_sent or slack_sent
