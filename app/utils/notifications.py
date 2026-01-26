"""
Notification service for sending alerts via email and Slack.

This module provides functions to send alert notifications to configured channels.
Notifications are optional and failures should not block alert creation.
"""

import os
import logging
from typing import Dict, Any, Optional
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

# Slack configuration
ALERT_SLACK_ENABLED = os.getenv('ALERT_SLACK_ENABLED', 'false').lower() == 'true'
ALERT_SLACK_WEBHOOK_URL = os.getenv('ALERT_SLACK_WEBHOOK_URL', '')
ALERT_SLACK_CHANNEL = os.getenv('ALERT_SLACK_CHANNEL', '#alerts')

# Try to import email libraries
try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False
    logger.warning("Email libraries not available. Install with: pip install email-validator")

# Try to import httpx for Slack webhooks
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available. Slack notifications will be disabled.")


def send_email_notification(alert_data: Dict[str, Any]) -> bool:
    """
    Send an alert notification via email.
    
    Args:
        alert_data: Dictionary containing alert data with keys:
            - alert_id: UUID
            - source: str
            - source_id: str
            - severity: str
            - message: str
            - details: dict (optional)
            - created_at: str
    
    Returns:
        True if email was sent successfully, False otherwise
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
    
    try:
        # Prepare email content
        alert_id = alert_data.get('alert_id', 'Unknown')
        source = alert_data.get('source', 'Unknown')
        source_id = alert_data.get('source_id', 'Unknown')
        severity = alert_data.get('severity', 'Unknown')
        message = alert_data.get('message', 'No message')
        details = alert_data.get('details', {})
        created_at = alert_data.get('created_at', 'Unknown')
        
        # Format email subject
        subject = f"[{severity.upper()}] Alert from {source}: {source_id}"
        
        # Format email body
        body = f"""
Alert Notification

Alert ID: {alert_id}
Source: {source}
Source ID: {source_id}
Severity: {severity}
Message: {message}
Created At: {created_at}
"""
        
        if details:
            body += f"\nDetails:\n{json.dumps(details, indent=2)}"
        
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = ALERT_EMAIL_FROM
        msg['To'] = ALERT_EMAIL_RECIPIENTS
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        with smtplib.SMTP(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(ALERT_EMAIL_SMTP_USER, ALERT_EMAIL_SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email notification sent for alert {alert_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        return False


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
            - created_at: str
    
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
        alert_id = alert_data.get('alert_id', 'Unknown')
        source = alert_data.get('source', 'Unknown')
        source_id = alert_data.get('source_id', 'Unknown')
        severity = alert_data.get('severity', 'Unknown')
        message = alert_data.get('message', 'No message')
        details = alert_data.get('details', {})
        created_at = alert_data.get('created_at', 'Unknown')
        
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
                            "value": created_at,
                            "short": True
                        }
                    ],
                    "footer": "Alert System"
                }
            ]
        }
        
        # Add timestamp if created_at is a datetime object
        try:
            from datetime import datetime
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
        # Note: Using sync httpx for simplicity, but could use async if needed
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


def send_alert_notification(alert_data: Dict[str, Any]) -> bool:
    """
    Send alert notifications via all configured channels.
    
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
            email_sent = send_email_notification(alert_data)
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
