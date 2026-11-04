from __future__ import annotations
import smtplib
from email.message import EmailMessage
from fastapi import HTTPException
from app.core.config import settings

def send_transactional_email(to_email: str, subject: str, html_body: str, text_body: str):
    provider = settings.email_provider.lower().strip()

    if provider == 'resend':
        if not settings.resend_api_key:
            # If in development and key is not set, provide clear explanation
            if settings.app_env.lower() == 'development':
                # Local dev fallback: log to console so developer is not blocked
                print(f"\n[DEV EMAIL NOTICE] To: {to_email} | Subject: {subject}\n{text_body}\n")
                return
            raise HTTPException(
                status_code=503,
                detail="Email delivery is not configured. Set RESEND_API_KEY in the backend .env file."
            )
        try:
            import resend
            resend.api_key = settings.resend_api_key
            result = resend.Emails.send({
                'from': settings.email_from,
                'to': [to_email],
                'subject': subject,
                'html': html_body,
                'text': text_body
            })
            if not result:
                raise RuntimeError("No provider response received from Resend.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Email provider rejected delivery: {str(e)}"
            ) from e

    elif provider == 'smtp':
        if not settings.smtp_host or not settings.email_from:
            if settings.app_env.lower() == 'development':
                print(f"\n[DEV EMAIL NOTICE] To: {to_email} | Subject: {subject}\n{text_body}\n")
                return
            raise HTTPException(
                status_code=503,
                detail="SMTP email delivery is not configured. Specify SMTP_HOST and credentials in backend .env."
            )
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = settings.email_from
        msg['To'] = to_email
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype='html')
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"SMTP server failed to send message: {str(e)}"
            ) from e
    else:
        raise HTTPException(status_code=503, detail="Unsupported EMAIL_PROVIDER. Configure 'resend' or 'smtp'.")

def build_otp_email(email: str, code: str, purpose: str = 'verify') -> tuple[str, str, str]:
    is_verify = purpose == 'verify'
    title = 'Verify your DataPilot AI email' if is_verify else 'Reset your DataPilot AI password'
    action_text = 'verify your new account' if is_verify else 'reset your account password'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:24px;background-color:#080b18;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#f3f4fd;">
      <div style="max-width:540px;margin:0 auto;background:linear-gradient(145deg,#13192f,#0e1326);border:1px solid rgba(139,124,255,0.25);border-radius:20px;padding:36px;box-shadow:0 20px 60px rgba(0,0,0,0.5);">
        <div style="display:flex;align-items:center;margin-bottom:24px;">
          <span style="display:inline-block;width:38px;height:38px;line-height:38px;text-align:center;background:linear-gradient(135deg,#8b7cff,#58e1ff);border-radius:10px;font-weight:900;color:#ffffff;font-size:18px;">DP</span>
          <span style="margin-left:12px;font-size:20px;font-weight:700;letter-spacing:-0.5px;color:#ffffff;">DataPilot <span style="color:#a89cff;">AI</span></span>
        </div>
        <h2 style="font-size:22px;font-weight:700;margin:0 0 12px;color:#ffffff;">{title}</h2>
        <p style="font-size:14px;line-height:1.6;color:#a3accb;margin:0 0 24px;">
          Use the 6-digit one-time passcode below to {action_text}.
        </p>
        <div style="text-align:center;padding:22px;background:#090d1e;border:1px dashed rgba(155,140,255,0.4);border-radius:14px;margin-bottom:24px;">
          <div style="font-size:36px;font-weight:800;letter-spacing:12px;color:#70e6ff;font-family:monospace;">
            {code}
          </div>
        </div>
        <p style="font-size:12px;line-height:1.6;color:#7883a4;margin:0 0 16px;">
          ⏱ This code will expire in <strong>{settings.otp_ttl_minutes} minutes</strong>. For your security, never share this code with anyone.
        </p>
        <div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:18px;margin-top:24px;font-size:11px;color:#5a6382;text-align:center;">
          If you did not request this email, no action is required and you can safely ignore it.
        </div>
      </div>
    </body>
    </html>
    """
    text = f"{title}\n\nYour one-time code is: {code}\n\nThis code expires in {settings.otp_ttl_minutes} minutes. Never share this code.\nIf you did not request this, you can ignore this email."
    return title, html, text
