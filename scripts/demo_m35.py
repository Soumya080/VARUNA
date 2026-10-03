"""
VARUNA GRID v2 — M3.5 End-to-End Demo.

Runs the full pipeline against the FastAPI backend.
"""
import requests
import time
import sys

API_URL = "http://localhost:8000/v1"

def print_banner(text):
    print(f"\n{'=' * 60}\n{text}\n{'=' * 60}")

def run_demo():
    print_banner("VARUNA GRID v2 — M3.5 PERSISTENT DEMO")
    
    # 1. Check health
    try:
        resp = requests.get("http://localhost:8000/health")
        if resp.status_code != 200:
            print("API not healthy. Exiting.")
            sys.exit(1)
    except Exception as e:
        print(f"Failed to connect to API: {e}")
        sys.exit(1)

    # 2. Create case
    print("[1] Creating CASE-0001...")
    resp = requests.post(f"{API_URL}/cases", json={"case_id": "CASE-0001"})
    resp.raise_for_status()
    case_id = resp.json()["case_id"]
    
    # 3. Ingest
    print(f"[2] Ingesting observations for {case_id}...")
    resp = requests.post(f"{API_URL}/cases/{case_id}/ingest", json={"use_fixture": "case_0001"})
    resp.raise_for_status()
    
    # 4. Reconstruct
    print("[3] Running backtracking reconstruction...")
    resp = requests.post(f"{API_URL}/cases/{case_id}/reconstruct", json={"seed": 42})
    resp.raise_for_status()
    
    # 5. Attribute
    print("[4] Attributing source to candidates...")
    resp = requests.post(f"{API_URL}/cases/{case_id}/attribute", json={"latent_prior": 0.5})
    resp.raise_for_status()
    
    # 6. Fetch results
    print("[5] Fetching final attribution results...")
    resp = requests.get(f"{API_URL}/cases/{case_id}")
    resp.raise_for_status()
    case_data = resp.json()
    
    attr_resp = requests.get(f"{API_URL}/cases/{case_id}/attribution")
    attr_resp.raise_for_status()
    attr_data = attr_resp.json()
    
    print_banner("DEMO COMPLETE")
    print(f"  Case ID:             {case_data['case_id']}")
    print(f"  Status:              {case_data['status']}")
    print(f"  Scientific Status:   {case_data['scientific_status']}")
    print(f"  Decision:            {attr_data['decision_state']}")
    print(f"  Latent Prob:         {attr_data['latent_probability']:.4f}")
    
    print("\nCandidates:")
    for c in attr_data["candidates"]:
        print(f"  Rank {c['rank']}: MMSI {c['mmsi']} (posterior={c['posterior']:.4f})")

if __name__ == "__main__":
    run_demo()
