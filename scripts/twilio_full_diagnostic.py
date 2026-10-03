"""Full Twilio diagnostic — checks EVERY possible reason SMS might not arrive."""
import os
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sid = os.environ["VARUNA_TWILIO_ACCOUNT_SID"]
token = os.environ["VARUNA_TWILIO_AUTH_TOKEN"]
auth = (sid, token)
base = f"https://api.twilio.com/2010-04-01/Accounts/{sid}"

print("=" * 60)
print("TWILIO FULL DIAGNOSTIC")
print("=" * 60)

# 1. Account info
print("\n--- 1. ACCOUNT STATUS ---")
r = httpx.get(f"{base}.json", auth=auth, timeout=15)
acct = r.json()
print(f"  Status:       {acct.get('status')}")
print(f"  Type:         {acct.get('type')}")
print(f"  Name:         {acct.get('friendly_name')}")
print(f"  Created:      {acct.get('date_created')}")

# 2. Balance
print("\n--- 2. ACCOUNT BALANCE ---")
r = httpx.get(f"{base}/Balance.json", auth=auth, timeout=15)
bal = r.json()
print(f"  Balance:      {bal.get('balance')} {bal.get('currency')}")
if float(bal.get('balance', 0)) <= 0:
    print("  *** CRITICAL: $0 balance. Twilio WILL NOT deliver messages! ***")

# 3. Phone numbers owned
print("\n--- 3. PHONE NUMBERS OWNED ---")
r = httpx.get(f"{base}/IncomingPhoneNumbers.json", auth=auth, timeout=15)
nums = r.json()
for n in nums.get("incoming_phone_numbers", []):
    print(f"  Number: {n['phone_number']}  SMS: {n.get('capabilities', {}).get('sms')}  Status: {n.get('status')}")
if not nums.get("incoming_phone_numbers"):
    print("  *** NO phone numbers found! ***")

# 4. Verified caller IDs (trial accounts can only send TO these)
print("\n--- 4. VERIFIED CALLER IDS (can send TO these on trial) ---")
r = httpx.get(f"{base}/OutgoingCallerIds.json", auth=auth, timeout=15)
cids = r.json()
for c in cids.get("outgoing_caller_ids", []):
    print(f"  Verified: {c['phone_number']}")
if not cids.get("outgoing_caller_ids"):
    print("  *** NO verified numbers! Cannot send SMS on trial! ***")

# 5. Recent messages and their ACTUAL status
print("\n--- 5. RECENT MESSAGES ---")
r = httpx.get(f"{base}/Messages.json?PageSize=10", auth=auth, timeout=15)
msgs = r.json()
print(f"  Total messages in log: {len(msgs.get('messages', []))}")
for m in msgs.get("messages", []):
    print(f"  SID: {m['sid']}")
    print(f"    Status: {m['status']}, Error: {m.get('error_code')} {m.get('error_message')}")
    print(f"    To: {m['to']}, From: {m['from']}")
    print(f"    Date: {m.get('date_sent')}")
if not msgs.get("messages"):
    print("  *** No messages found in account log ***")

# 6. Try sending and immediately check
print("\n--- 6. SEND TEST + IMMEDIATE STATUS ---")
r = httpx.post(
    f"{base}/Messages.json",
    auth=auth,
    data={
        "To": "+919977646003",
        "From": "+17372212163",
        "Body": "VARUNA Alert Test - if you see this, SMS is working!",
    },
    timeout=15,
)
print(f"  HTTP Status: {r.status_code}")
send_data = r.json()
print(f"  SID:          {send_data.get('sid')}")
print(f"  Status:       {send_data.get('status')}")
print(f"  Error Code:   {send_data.get('error_code')}")
print(f"  Error Msg:    {send_data.get('error_message')}")
print(f"  Body:         {send_data.get('body', '')[:100]}")

# 7. Check notifications/alerts on the account
print("\n--- 7. ACCOUNT NOTIFICATIONS (errors/warnings) ---")
r = httpx.get(f"{base}/Notifications.json?PageSize=5", auth=auth, timeout=15)
if r.status_code == 200:
    notifs = r.json()
    for n in notifs.get("notifications", []):
        print(f"  [{n.get('log')}] {n.get('message_text', '')[:120]}")
    if not notifs.get("notifications"):
        print("  No notifications/warnings found.")
else:
    print(f"  Could not fetch notifications: HTTP {r.status_code}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
