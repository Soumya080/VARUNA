"""HACKATHON JUDGE TEST — cold, adversarial walkthrough of the running product.

No prior knowledge assumed. Clicks what a judge would click, in order, and
records what actually happens including every network failure.
"""
from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import sync_playwright

FE = "http://localhost:3000"
DL = os.path.abspath("reports/product/_judge_downloads")
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(f"{label}: {detail}")


def main() -> int:
    console_errors: list[str] = []
    netfail: list[str] = []
    calls: list[str] = []
    os.makedirs(DL, exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1720, "height": 1400}, accept_downloads=True)
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: netfail.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: netfail.append(f"{r.method} {r.url} :: {r.failure}"))
        page.on("response",
                lambda r: calls.append(f"{r.status} {r.request.method} {r.url.split('8000')[-1]}")
                if "/v1/" in r.url else None)

        def body() -> str:
            return page.locator("body").inner_text()

        print("### 1. Judge opens the app cold")
        page.goto(FE, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(4000)
        t = body()
        check("Landing page explains what the system is", "Mission Cockpit" in t)
        check("Story strip visible", "OBSERVE" in t and "AUTHORIZE" in t)
        check("Not-signed-in state is honest", "Not signed in" in t)

        print("\n### 2. Judge signs in")
        w = page.locator('header button[aria-haspopup="menu"]').first
        w.click(); page.wait_for_timeout(500)
        page.locator('header input[autocomplete="username"]').first.fill("officer")
        page.locator('header input[autocomplete="current-password"]').first.fill("officer-demo-pass")
        page.locator('header button[type="submit"]').first.click()
        page.wait_for_timeout(2500)
        check("Login works", "Duty Officer" in w.inner_text(), w.inner_text().replace("\n", " "))

        print("\n### 3. Judge clicks RUN VARUNA")
        page.get_by_role("button", name=re.compile("Run VARUNA", re.I)).first.click()
        page.wait_for_timeout(8000)
        t = body()
        stages = ["Data / forcing", "NETRA detection", "Starting point", "PRATIVARTAN",
                  "PRAVAAH", "CHHAYA", "NYAYA", "Validity gate", "Alert", "PRAMAN"]
        missing = [s for s in stages if s not in t]
        check("All pipeline stages appear in the timeline", not missing, f"missing {missing}")

        print("\n### 4. Judge looks at the map")
        check("Map tiles rendered", page.locator("img.leaflet-tile").count() > 0,
              f"{page.locator('img.leaflet-tile').count()} tiles")
        check("Vector layers drawn", page.locator(".leaflet-overlay-pane path").count() > 0,
              f"{page.locator('.leaflet-overlay-pane path').count()} paths")
        check("Layer switcher present (satellite/ocean/street)",
              page.locator(".leaflet-control-layers").count() > 0)
        check("Scale bar present", page.locator(".leaflet-control-scale").count() > 0)
        check("Starting point labelled on map", "STARTING POINT" in t)
        check("Gulf of Mexico coordinates shown", "88.970" in t and "28.936" in t)

        print("\n### 5. Judge checks the Alert Center")
        ac = page.locator("#alert-center")
        check("Alert Center exists", ac.count() > 0)
        atxt = ac.inner_text() if ac.count() else ""
        check("Alerts were generated", bool(re.search(r"ALERT CENTER \((\d+)\)", atxt))
              and "ALERT CENTER (0)" not in atxt, re.search(r"ALERT CENTER \(\d+\)", atxt).group(0) if atxt else "")
        check("Severity shown", any(x in atxt for x in ("HIGH", "MEDIUM", "CRITICAL")))
        check("Routing shown", "DUTY OFFICER" in atxt.upper())
        check("External authorities routed for landfall",
              "STATE PCB" in atxt.upper() and "DG SHIPPING" in atxt.upper())
        check("Channel status honest (NOT_CONFIGURED visible)", "NOT_CONFIGURED" in atxt)
        check("Nothing claims fake delivery success", "SUCCESS" not in atxt)

        print("\n### 6. Judge clicks Acknowledge")
        ackb = ac.get_by_role("button", name=re.compile("^Acknowledge$"))
        if ackb.count():
            ackb.first.click(); page.wait_for_timeout(3000)
            check("Acknowledge confirmed by backend", "confirmed by backend" in body())
        else:
            check("Acknowledge button available", False, "no button rendered")

        print("\n### 7. Judge clicks Escalate")
        escb = page.locator("#alert-center").get_by_role("button", name=re.compile("^Escalate$"))
        if escb.count():
            escb.first.click(); page.wait_for_timeout(3000)
            check("Escalate confirmed by backend", "confirmed by backend" in body())
        else:
            check("Escalate button available", False, "no button rendered")

        print("\n### 8. Judge authorizes the mission")
        mcard = page.locator('section:has(h3:text-is("Mission"))').first
        authb = page.get_by_role("button", name=re.compile("Authorize mission", re.I))
        check("Authorize button present and enabled", authb.count() > 0 and authb.first.is_enabled(),
              mcard.inner_text().replace("\n", " | ")[:110] if mcard.count() else "")
        if authb.count() and authb.first.is_enabled():
            authb.first.click(); page.wait_for_timeout(3500)
            mt = mcard.inner_text()
            check("Mission authorization confirmed", "confirmed by backend" in body())
            check("Mission card now shows ASSIGNED/Authorized",
                  "ASSIGNED" in mt.upper() or "AUTHORIZED BY" in mt.upper(),
                  mt.replace("\n", " | ")[:110])
            # judge clicks again — must NOT error
            authb2 = page.get_by_role("button", name=re.compile("Authorize mission", re.I))
            check("Authorize button no longer clickable after success (no repeat 400)",
                  authb2.count() == 0)

        print("\n### 9. Judge tries CHHAYA")
        ch = page.locator("#chhaya-v2")
        check("CHHAYA panel present", ch.count() > 0)
        if ch.count():
            inv = ch.get_by_role("button", name=re.compile("Investigate tile", re.I))
            if inv.count():
                inv.first.click(); page.wait_for_timeout(6000)
                ct = ch.inner_text()
                check("CHHAYA ran on real SAR", "cfar_ca_v1" in ct or "CFAR" in ct.upper(), ct.replace("\n"," | ")[:130])
                check("CHHAYA declares outcome", any(o in ct.lower() for o in
                      ("no supported vessel", "known vessel", "dark vessel", "inconclusive")))
                check("CHHAYA discloses uncalibrated scoring", "relative plausibility" in ct.lower())

        print("\n### 10. Judge downloads the report")
        try:
            with page.expect_download(timeout=45000) as dl:
                page.get_by_role("link", name=re.compile("Download report", re.I)).first.click()
            d = dl.value
            path = os.path.join(DL, d.suggested_filename)
            d.save_as(path)
            with open(path, "rb") as fh:
                head = fh.read(5)
            check("Report downloads as a real PDF", head == b"%PDF-",
                  f"{d.suggested_filename} {os.path.getsize(path)} bytes")
        except Exception as exc:
            check("Report downloads as a real PDF", False, f"{type(exc).__name__}: {str(exc)[:90]}")

        print("\n### 11. Judge probes the failure path (CASE-OOD)")
        page.get_by_role("button", name="CASE-OOD", exact=True).first.click()
        page.wait_for_timeout(2500)
        page.get_by_role("button", name=re.compile("Run VARUNA", re.I)).first.click()
        page.wait_for_timeout(8000)
        ot = body()
        check("OOD: no starting point fabricated", "STARTING_POINT_UNAVAILABLE" in ot)
        check("OOD: no alerts fabricated", "No alerts for this case" in ot)
        check("OOD: recommendation unavailable", "unavailable" in ot.lower())

        print("\n### 12. Judge checks unauthorized access")
        page.get_by_role("button", name="CASE-VALID", exact=True).first.click()
        page.wait_for_timeout(2500)
        page.locator('header button[aria-haspopup="menu"]').first.click(); page.wait_for_timeout(400)
        page.locator('header button:has-text("Log Out")').first.click(); page.wait_for_timeout(1200)
        check("Logout works", "Not signed in" in body())
        w2 = page.locator('header button[aria-haspopup="menu"]').first
        w2.click(); page.wait_for_timeout(400)
        page.locator('header input[autocomplete="username"]').first.fill("analyst")
        page.locator('header input[autocomplete="current-password"]').first.fill("analyst-demo-pass")
        page.locator('header button[type="submit"]').first.click(); page.wait_for_timeout(2500)
        esc3 = page.locator("#alert-center").get_by_role("button", name=re.compile("^Escalate$"))
        if esc3.count():
            esc3.first.click(); page.wait_for_timeout(2500)
            check("Analyst escalate denied with honest message", "NOT AUTHORIZED" in body())
        else:
            print("   [INFO] no escalate action available in current alert states")

        print("\n### 13. Network hygiene")
        check("No failed network requests", not netfail, str(netfail)[:150])
        unexpected = [c for c in calls if not c.startswith(("200", "304"))
                      and "/escalate" not in c and "/approve" not in c]
        check("No unexpected non-200 responses", not unexpected, str(unexpected)[:150])
        breaking = [c for c in console_errors if "Failed to load resource" not in c]
        check("No breaking console errors", not breaking, str(sorted(set(breaking))[:2])[:150])

        page.screenshot(path="reports/product/judge_view.png")
        b.close()

    print("\n" + "=" * 62)
    if FAILS:
        print(f"JUDGE VERDICT: {len(FAILS)} ISSUE(S)")
        for f in FAILS:
            print("  -", f)
    else:
        print("JUDGE VERDICT: ALL CHECKS PASSED")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
