"""Check Twilio message delivery status."""
import os
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sid = os.environ["VARUNA_TWILIO_ACCOUNT_SID"]
token = os.environ["VARUNA_TWILIO_AUTH_TOKEN"]

# Fetch the last 5 messages from Twilio
r = httpx.get(
    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?PageSize=5",
    auth=(sid, token),
    timeout=15,
)
data = r.json()
print(f"=== Last {len(data.get('messages', []))} Twilio Messages ===\n")
for m in data.get("messages", []):
    print(f"SID:           {m['sid']}")
    print(f"  To:          {m['to']}")
    print(f"  From:        {m['from']}")
    print(f"  Status:      {m['status']}")
    print(f"  Error Code:  {m['error_code']}")
    print(f"  Error Msg:   {m['error_message']}")
    print(f"  Date Sent:   {m['date_sent']}")
    print(f"  Body:        {m['body'][:80]}")
    print()
