"""Phase 6 - do human decisions survive an API restart?

Acknowledgements, escalations and mission approvals used to live only in
memory, so a restart silently erased every decision an operator had made.
Phase 1 moved them to JSONL. This asserts that it actually worked, against a
real process restart rather than a simulated one.

Deliberately makes NO assertion about anything it did not first observe: it
records live state, restarts, and compares. It never writes fixture data.

Usage:  python scripts/restart_survival_check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8000"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print("   [" + ("PASS" if ok else "FAIL") + "] " + label + (" - " + detail if detail else ""))
    if not ok:
        FAILS.append(label)


def api(path: str, method: str = "GET", token: str | None = None,
        payload: dict | None = None, timeout: int = 20):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as exc:
        return 0, type(exc).__name__ + ": " + str(exc)


def uvicorn_procs() -> list[tuple[int, str]]:
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*uvicorn*' } | "
        "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        if "|" in line:
            pid, _, cmd = line.partition("|")
            rows.append((int(pid.strip()), cmd.strip()))
    return rows


def snapshot(token: str) -> dict:
    """Everything a restart could plausibly lose."""
    _, alerts = api("/v1/alerts?limit=500", token=token)
    items = alerts.get("items", []) if isinstance(alerts, dict) else []
    _, cases = api("/v1/cases", token=token)
    citems = cases.get("items", []) if isinstance(cases, dict) else []
    missions = []
    for c in citems:
        _, m = api("/v1/cases/" + c["case_id"] + "/missions", token=token)
        if isinstance(m, dict):
            missions.extend(m.get("items", []))
    return {
        "alert_states": {a["alert_id"]: a.get("status") for a in items},
        "mission_states": {m["mission_id"]: m.get("state") for m in missions},
        "mission_approvals": {m["mission_id"]: m.get("human_approved_by") for m in missions},
        "n_cases": len(citems),
    }


def wait_up(deadline: int = 90) -> bool:
    for _ in range(deadline):
        st, _ = api("/health", timeout=3)
        if st == 200:
            return True
        time.sleep(1)
    return False


def main() -> int:
    procs = uvicorn_procs()
    print("### 0. Preconditions")
    check("Exactly one uvicorn process is running", len(procs) == 1,
          "found " + str(len(procs)) + ": " + str([p for p, _ in procs]))
    if len(procs) != 1:
        print()
        print("   Two API processes hold divergent in-memory state - the JSONL")
        print("   stores never re-read from disk. Restart-survival cannot be")
        print("   measured reliably until only one is running. Aborting rather")
        print("   than reporting a result that may be meaningless.")
        return 1

    pid, cmdline = procs[0]
    st, tokresp = api("/v1/auth/login", "POST",
                      payload={"username": "officer", "password": "officer-demo-pass"})
    token = tokresp.get("access_token") if isinstance(tokresp, dict) else None
    check("Authenticated against the running API", bool(token), "HTTP " + str(st))
    if not token:
        return 1

    print()
    print("### 1. Record live state")
    before = snapshot(token)
    print("   alerts=" + str(len(before["alert_states"]))
          + " missions=" + str(len(before["mission_states"]))
          + " cases=" + str(before["n_cases"]))
    check("There is decision state worth testing",
          bool(before["alert_states"]) or bool(before["mission_states"]),
          "nothing recorded yet - run a case first")
    if not (before["alert_states"] or before["mission_states"]):
        return 1

    print()
    print("### 2. Restart the API process (pid " + str(pid) + ")")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Id " + str(pid) + " -Force"], capture_output=True)
    time.sleep(3)
    subprocess.Popen(cmdline, shell=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    check("API came back up", wait_up())

    print()
    print("### 3. Compare")
    st, tokresp = api("/v1/auth/login", "POST",
                      payload={"username": "officer", "password": "officer-demo-pass"})
    token2 = tokresp.get("access_token") if isinstance(tokresp, dict) else None
    check("Login still works after restart", bool(token2))
    after = snapshot(token2 or "")

    check("No alert was lost",
          set(before["alert_states"]) <= set(after["alert_states"]),
          str(len(before["alert_states"])) + " -> " + str(len(after["alert_states"])))
    lost = [k for k, v in before["alert_states"].items() if after["alert_states"].get(k) != v]
    check("Every alert kept its lifecycle status (acks/escalations survived)",
          not lost, "changed: " + str(lost[:4]))
    check("No mission was lost",
          set(before["mission_states"]) <= set(after["mission_states"]),
          str(len(before["mission_states"])) + " -> " + str(len(after["mission_states"])))
    mlost = [k for k, v in before["mission_states"].items() if after["mission_states"].get(k) != v]
    check("Every mission kept its FSM state", not mlost, "changed: " + str(mlost[:4]))
    alost = [k for k, v in before["mission_approvals"].items()
             if v and after["mission_approvals"].get(k) != v]
    check("Human mission approvals survived", not alost, "lost: " + str(alost[:4]))
    check("Case list survived", after["n_cases"] >= before["n_cases"],
          str(before["n_cases"]) + " -> " + str(after["n_cases"]))

    print()
    print("=" * 62)
    print("RESTART SURVIVAL: " + ("ALL CHECKS PASSED" if not FAILS
                                  else str(len(FAILS)) + " ISSUE(S)"))
    for f in FAILS:
        print("  -", f)
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
