# Feedback report email sender.
from email.message import EmailMessage
import smtplib

from app.config import Settings


class FeedbackMailer:
    # Sends feedback reports via SMTP.

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, *, subject: str, body: str) -> None:
        recipient = (self._settings.feedback_report_email or "").strip()
        if not recipient:
            raise ValueError("feedback report email is not configured")

        sender = (self._settings.public_contact_email or "").strip() or "no-reply@localhost"
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body)

        try:
            if self._settings.smtp_use_ssl:
                smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                    self._settings.smtp_host,
                    self._settings.smtp_port,
                    timeout=10,
                )
            else:
                smtp = smtplib.SMTP(
                    self._settings.smtp_host,
                    self._settings.smtp_port,
                    timeout=10,
                )
            with smtp:
                if self._settings.smtp_use_tls and not self._settings.smtp_use_ssl:
                    smtp.starttls()
                if (self._settings.smtp_username or "").strip():
                    smtp.login(self._settings.smtp_username, self._settings.smtp_password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise
