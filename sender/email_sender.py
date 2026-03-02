"""
Sends the weekly HTML report as the email body via Gmail SMTP.

Setup:
  1. Enable 2-Step Verification on your Google account
  2. Go to https://myaccount.google.com/apppasswords
  3. Generate an App Password for "Mail"
  4. Set EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENTS in .env
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import config

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def send_report(html_path: str) -> bool:
    """
    Send the HTML file at html_path as the email body.
    Returns True on success, False on failure.
    """
    if not config.email_sender:
        logger.warning("EMAIL_SENDER not set — skipping email.")
        return False
    if not config.email_app_password:
        logger.warning("EMAIL_APP_PASSWORD not set — skipping email.")
        return False
    if not config.email_recipients:
        logger.warning("EMAIL_RECIPIENTS not set — skipping email.")
        return False

    html_content = Path(html_path).read_text(encoding="utf-8")
    recipients = [r.strip() for r in config.email_recipients.split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = _subject()
    msg["From"] = config.email_sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(config.email_sender, config.email_app_password)
            smtp.sendmail(config.email_sender, recipients, msg.as_string())
        logger.info("Email sent to: %s", ", ".join(recipients))
        return True
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return False


def _subject() -> str:
    from datetime import datetime
    return f"AI Weekly — {datetime.now().strftime('%B %d, %Y')}"
