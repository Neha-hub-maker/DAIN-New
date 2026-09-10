import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_verification_email(to_email: str, token: str) -> None:
    if not all(
        [
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.email_from,
        ]
    ):
        raise RuntimeError("Email delivery is not configured.")

    message = EmailMessage()
    message["Subject"] = "DAIN email verification"
    message["From"] = settings.email_from
    message["To"] = to_email

    message.set_content(
        f"""Welcome to DAIN.

Your verification code is:

{token}

This code expires in {settings.verification_token_ttl_minutes} minutes.

If you did not request this account, ignore this email.
"""
    )

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=15,
        ) as server:
            server.login(
                settings.smtp_username,
                settings.smtp_password,
            )
            server.send_message(message)
    else:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=15,
        ) as server:
            server.starttls()
            server.login(
                settings.smtp_username,
                settings.smtp_password,
            )
            server.send_message(message)