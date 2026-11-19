import httpx, json

# Step 1: Login to get a JWT
login_resp = httpx.post(
    "http://localhost:8000/v1/auth/login",
    json={"username": "admin", "password": "admin-demo-pass"},
    timeout=10,
)
print("Login status:", login_resp.status_code)
if login_resp.status_code != 200:
    print("Login failed:", login_resp.text)
    exit(1)

token = login_resp.json()["access_token"]
print("Got token:", token[:20] + "...")

# Step 2: Send test notification with the JWT
resp = httpx.post(
    "http://localhost:8000/v1/alerts/test-notification",
    json={"role": "operator", "channels": ["email"]},
    headers={"Authorization": f"Bearer {token}"},
    timeout=15,
)
print("\nTest notification status:", resp.status_code)
data = resp.json()
for r in data.get("results", []):
    print(f"  {r['channel']}: {r['status']} via {r.get('provider','?')}")
    print(f"  detail: {r.get('detail') or r.get('error')}")
