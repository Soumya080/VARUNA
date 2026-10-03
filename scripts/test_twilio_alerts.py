"""Quick test: fire a Twilio SMS and Email using the VARUNA alert layer."""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Verify env vars are loaded
print("=== ENV CHECK ===")
print(f"  VARUNA_SMS_PROVIDER       = {os.environ.get('VARUNA_SMS_PROVIDER')}")
print(f"  VARUNA_TWILIO_ACCOUNT_SID = {os.environ.get('VARUNA_TWILIO_ACCOUNT_SID', 'NOT SET')[:10]}...")
print(f"  VARUNA_TWILIO_AUTH_TOKEN  = {'SET' if os.environ.get('VARUNA_TWILIO_AUTH_TOKEN') else 'NOT SET'}")
print(f"  VARUNA_TWILIO_FROM_PHONE  = {os.environ.get('VARUNA_TWILIO_FROM_PHONE')}")
print(f"  VARUNA_ALERT_PHONE        = {os.environ.get('VARUNA_ALERT_PHONE')}")
print(f"  VARUNA_EMAIL_PROVIDER     = {os.environ.get('VARUNA_EMAIL_PROVIDER')}")
print(f"  VARUNA_TWILIO_EMAIL_KEY   = {'SET' if os.environ.get('VARUNA_TWILIO_EMAIL_KEY') else 'NOT SET'}")
print(f"  VARUNA_ALERT_TO           = {os.environ.get('VARUNA_ALERT_TO')}")
print()

# Add packages to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

# --- Test SMS ---
print("=== SMS TEST ===")
from varuna_alerts.channels.sms_gateway import sms_provider_status, send_sms

status = sms_provider_status()
print(f"  Provider status: {status}")

if status["mode"] == "REAL":
    result = send_sms(
        alert_id="TEST-SMS-001",
        recipient_role="duty_officer",
        phone=os.environ.get("VARUNA_ALERT_PHONE", "+919977646003"),
        body="[VARUNA TEST] Oil spill alert detected near Mumbai coast. Case CASE-TEST-001. This is a test notification from VARUNA GRID.",
    )
    print(f"  SMS Result: status={result.status}, provider={result.provider}")
    print(f"  Detail: {result.detail}")
    if result.error:
        print(f"  ERROR: {result.error}")
else:
    print(f"  SKIPPED — SMS not configured: {status['reason']}")

print()

# --- Test Email ---
print("=== EMAIL TEST ===")
from varuna_alerts.channel_orchestrator import _email

email_result = _email(
    alert_id="TEST-EMAIL-001",
    role="duty_officer",
    subject="[VARUNA TEST] Oil Spill Alert - Case CASE-TEST-001",
    body="Oil spill detected near Mumbai coast. Vessel MV TESTSHIP is the primary suspect with posterior probability 0.82. Immediate action required.",
)
print(f"  Email Result: status={email_result.status}, provider={email_result.provider}")
print(f"  Detail: {email_result.detail}")
if email_result.error:
    print(f"  ERROR: {email_result.error}")

print()
print("=== DONE ===")
