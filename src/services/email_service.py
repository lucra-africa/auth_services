import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import settings

logger = logging.getLogger(__name__)


def _build_verify_email_html(verify_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">Poruta</h2>
  <p>Hi,</p>
  <p>Thank you for creating a Poruta account. Please verify your email address by clicking the button below.</p>
  <p style="text-align: center; margin: 30px 0;">
    <a href="{verify_url}" style="background-color: #1a1a2e; color: #ffffff; padding: 12px 30px;
       text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
      Verify Email Address
    </a>
  </p>
  <p style="color: #666; font-size: 14px;">This link expires in 24 hours.</p>
  <p style="color: #666; font-size: 14px;">If you didn't create an account, you can safely ignore this email.</p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
  <p style="color: #999; font-size: 12px;">&copy; 2026 Poruta. All rights reserved.</p>
</body>
</html>"""


def _build_invitation_email_html(
    inviter_name: str, role_label: str, accept_url: str, agency_name: str | None = None
) -> str:
    agency_line = f"<p>You'll be joining <strong>{agency_name}</strong>.</p>" if agency_name else ""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">Poruta</h2>
  <p>Hi,</p>
  <p><strong>{inviter_name}</strong> has invited you to join Poruta as a <strong>{role_label}</strong>.</p>
  {agency_line}
  <p style="text-align: center; margin: 30px 0;">
    <a href="{accept_url}" style="background-color: #1a1a2e; color: #ffffff; padding: 12px 30px;
       text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
      Accept Invitation
    </a>
  </p>
  <p style="color: #666; font-size: 14px;">This invitation expires in 24 hours.</p>
  <p style="color: #666; font-size: 14px;">If you weren't expecting this invitation, you can safely ignore this email.</p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
  <p style="color: #999; font-size: 12px;">&copy; 2026 Poruta. All rights reserved.</p>
</body>
</html>"""


def _build_password_reset_email_html(reset_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">Poruta</h2>
  <p>Hi,</p>
  <p>We received a request to reset your password.</p>
  <p style="text-align: center; margin: 30px 0;">
    <a href="{reset_url}" style="background-color: #1a1a2e; color: #ffffff; padding: 12px 30px;
       text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">
      Reset Password
    </a>
  </p>
  <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
  <p style="color: #666; font-size: 14px;">If you didn't request a password reset, your account is still secure. You can safely ignore this email.</p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
  <p style="color: #999; font-size: 12px;">&copy; 2026 Poruta. All rights reserved.</p>
</body>
</html>"""


ROLE_LABELS = {
    "agent": "Customs Agent",
    "inspector": "Customs Inspector",
    "government": "Government Official",
    "agency_manager": "Agency Manager",
}


def _send_smtp(to: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send — run in thread pool."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


async def _send_email(to: str, subject: str, html_body: str) -> None:
    if settings.app_env == "development" and not settings.smtp_password:
        logger.info("DEV MODE — Email to %s | Subject: %s", to, subject)
        return
    try:
        await asyncio.to_thread(_send_smtp, to, subject, html_body)
    except Exception:
        logger.exception("Failed to send email to %s", to)


async def send_verification_email(to_email: str, token: str) -> None:
    url = f"{settings.frontend_url}/verify-email?token={token}"
    html = _build_verify_email_html(url)
    await _send_email(to_email, "Verify your Poruta account", html)


async def send_invitation_email(
    to_email: str, token: str, inviter_name: str, role: str, agency_name: str | None = None
) -> None:
    url = f"{settings.frontend_url}/signup/invite?token={token}"
    role_label = ROLE_LABELS.get(role, role)
    html = _build_invitation_email_html(inviter_name, role_label, url, agency_name)
    await _send_email(to_email, "You've been invited to join Poruta", html)


async def send_password_reset_email(to_email: str, token: str) -> None:
    url = f"{settings.frontend_url}/reset-password?token={token}"
    html = _build_password_reset_email_html(url)
    await _send_email(to_email, "Reset your Poruta password", html)
