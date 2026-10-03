"""Workstream A — real Chromium end-to-end acceptance.

LOGIN -> CASE-VALID -> evidence -> material change -> alert -> routing ->
notification -> ACK -> escalation -> mission authorization -> PRAMAN ->
SMRITI -> report download, plus the failure paths.
"""
from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import sync_playwright

FE = "http://localhost:3000"
DL = os.path.abspath("reports/product/_downloads")


def main() -> int:
    console_errors: list[str] = []
    failures: list[str] = []
    calls: list[str] = []
    os.makedirs(DL, exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1700, "height": 1400}, accept_downloads=True)
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: failures.append(f"pageerror: {e}"))
        page.on("requestfailed",
                lambda r: failures.append(f"{r.method} {r.url} :: {r.failure}"))
        page.on("response",
                lambda r: calls.append(f"{r.status} {r.request.method} {r.url.split('8000')[-1]}")
                if "/v1/" in r.url else None)

        def sign_in(u: str, pw: str) -> str:
            w = page.locator('header button[aria-haspopup="menu"]').first
            w.click(); page.wait_for_timeout(400)
            page.locator('header input[autocomplete="username"]').first.fill(u)
            page.locator('header input[autocomplete="current-password"]').first.fill(pw)
            page.locator('header button[type="submit"]').first.click()
            page.wait_for_timeout(2200)
            return w.inner_text().replace("\n", " | ")

        def body() -> str:
            return page.locator("body").inner_text()

        print("=== 1. LOGIN as officer ===")
        page.goto(FE, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(3000)
        print("   identity:", sign_in("officer", "officer-demo-pass"))

        print("\n=== 2-3. CASE-VALID + RUN VARUNA (material change -> alerts) ===")
        page.get_by_role("button", name=re.compile("Run VARUNA", re.I)).first.click()
        page.wait_for_timeout(7000)

        ac = page.locator("#alert-center")
        print("   Alert Center present:", ac.count() > 0)
        header = ac.locator("h3").first.inner_text() if ac.count() else "?"
        print("   ", header)

        print("\n=== 4. channel status (honest modes) ===")
        for ln in ac.inner_text().splitlines()[:6]:
            if ":" in ln and any(m in ln for m in ("REAL", "SIMULATED", "NOT_CONFIGURED")):
                print("   ", ln.strip()[:110])

        print("\n=== 5. alerts: severity / dimension / routing ===")
        txt = ac.inner_text()
        for ln in txt.splitlines():
            if re.search(r"(high|medium|critical|low)\b|detection\.|attribution\.|validity\.|"
                         r"landfall\.|duty officer|supervisor|state pcb|dg shipping", ln, re.I):
                s = ln.strip()
                if s:
                    print("   ", s[:110])

        print("\n=== 6. expand an alert -> delivery + transitions ===")
        det = ac.get_by_role("button", name=re.compile("^Detail$"))
        if det.count():
            det.first.click(); page.wait_for_timeout(900)
            for ln in ac.inner_text().splitlines():
                if re.search(r"NOT_CONFIGURED|SIMULATED|REAL|created|routed|delivery_pending|"
                             r"delivered|Severity basis|Routing rule", ln):
                    s = ln.strip()
                    if s:
                        print("   ", s[:110])

        print("\n=== 7. ACKNOWLEDGE (real backend) ===")
        ack = ac.get_by_role("button", name=re.compile("^Acknowledge$"))
        if ack.count():
            ack.first.click(); page.wait_for_timeout(3000)
            for ln in body().splitlines():
                if "confirmed by backend" in ln or "NOT AUTH" in ln:
                    print("   ->", ln.strip()[:100])

        print("\n=== 8. ESCALATE ===")
        esc = page.locator("#alert-center").get_by_role("button", name=re.compile("^Escalate$"))
        if esc.count():
            esc.first.click(); page.wait_for_timeout(3000)
            for ln in body().splitlines():
                if "confirmed by backend" in ln or "NOT AUTH" in ln:
                    print("   ->", ln.strip()[:100])

        print("\n=== 9. MISSION AUTHORIZATION ===")
        auth = page.get_by_role("button", name=re.compile("Authorize mission", re.I))
        if auth.count():
            auth.first.click(); page.wait_for_timeout(3000)
            mcard = page.locator('section:has(h3:text-is("Mission"))').first
            print("   MISSION:", mcard.inner_text().replace("\n", " | ")[:150])
            for ln in body().splitlines():
                if "confirmed by backend" in ln or "NOT AUTH" in ln:
                    print("   ->", ln.strip()[:100])

        print("\n=== 10. PRAMAN ===")
        pc = page.locator("#praman-card").first
        if pc.count():
            print("   ", pc.inner_text().replace("\n", " | ")[:190])

        print("\n=== 11. REPORT DOWNLOAD ===")
        try:
            with page.expect_download(timeout=45000) as dl:
                page.get_by_role("link", name=re.compile("Download incident report", re.I)).first.click()
            d = dl.value
            path = os.path.join(DL, d.suggested_filename)
            d.save_as(path)
            with open(path, "rb") as fh:
                head = fh.read(5)
            print(f"   downloaded {d.suggested_filename} "
                  f"({os.path.getsize(path)} bytes) header={head!r} isPDF={head == b'%PDF-'}")
        except Exception as exc:
            print("   DOWNLOAD FAILED:", type(exc).__name__, str(exc)[:150])

        print("\n=== 12. FAILURE PATH: unauthorized (analyst escalate) ===")
        page.locator('header button[aria-haspopup="menu"]').first.click(); page.wait_for_timeout(400)
        page.locator('header button:has-text("Log Out")').first.click(); page.wait_for_timeout(1200)
        print("   analyst:", sign_in("analyst", "analyst-demo-pass"))
        esc2 = page.locator("#alert-center").get_by_role("button", name=re.compile("^Escalate$"))
        if esc2.count():
            esc2.first.click(); page.wait_for_timeout(2500)
            for ln in body().splitlines():
                if "NOT AUTHORIZED" in ln or "confirmed by backend" in ln:
                    print("   ->", ln.strip()[:110])
        else:
            print("   (no escalate action available in current alert states)")

        print("\n=== 13. FAILURE PATH: CASE-OOD fail-closed ===")
        page.get_by_role("button", name="CASE-OOD", exact=True).first.click()
        page.wait_for_timeout(2500)
        page.get_by_role("button", name=re.compile("Run VARUNA", re.I)).first.click()
        page.wait_for_timeout(7000)
        ood = body()
        for ln in ood.splitlines():
            if re.search(r"No alerts for this case|STARTING_POINT_UNAVAILABLE|"
                         r"No geographic|no alert is fabricated|unavailable", ln, re.I):
                print("   ", ln.strip()[:115])

        print("\n=== network ===")
        print("   failed requests:", failures or "NONE")
        non200 = [c for c in calls if not c.startswith(("200", "304"))]
        print("   non-200 /v1/:", non200 or "NONE")
        print("   console errors:",
              sorted({re.sub(r'\s+', ' ', c)[:90] for c in console_errors}) or "NONE")

        page.screenshot(path="reports/product/workstream_a_cockpit.png")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
