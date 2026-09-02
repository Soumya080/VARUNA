"""VARUNA Mission Cockpit — real Chromium acceptance test.

Drives the actual running stack through the full operator story and the
fail-closed story, recording what a human would see plus every network
failure and console error.
"""
from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

FE = "http://localhost:3000"


def main() -> int:
    console_errors: list[str] = []
    failed_requests: list[str] = []
    calls: list[str] = []

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1700, "height": 1300})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: failed_requests.append(f"pageerror: {e}"))
        page.on("requestfailed",
                lambda r: failed_requests.append(f"{r.method} {r.url} :: {r.failure}"))
        page.on("response",
                lambda r: calls.append(f"{r.status} {r.request.method} {r.url.split('8000')[-1]}")
                if "/v1/" in r.url else None)

        def sign_in(u: str, pw: str) -> str:
            w = page.locator('header button[aria-haspopup="menu"]').first
            w.click(); page.wait_for_timeout(400)
            page.locator('header input[autocomplete="username"]').first.fill(u)
            page.locator('header input[autocomplete="current-password"]').first.fill(pw)
            page.locator('header button[type="submit"]').first.click()
            page.wait_for_timeout(2000)
            return w.inner_text().replace("\n", " | ")

        def body() -> str:
            return page.locator("body").inner_text()

        print("=== 1-2. open cockpit + login as officer ===")
        page.goto(FE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2500)
        print("   identity:", sign_in("officer", "officer-demo-pass"))

        print("\n=== 3-4. RUN VARUNA (CASE-VALID) + watch stages ===")
        page.get_by_role("button", name=re.compile("Run VARUNA", re.I)).first.click()
        page.wait_for_timeout(6000)
        t = body()
        stages = [l.strip() for l in t.splitlines()
                  if re.search(r"(NETRA detection|PRATIVARTAN|PRAVAAH|CHHAYA|NYAYA|Validity gate|"
                               r"Starting point|Next best action|PRAMAN provenance|Alert$|Mission$|"
                               r"Data / forcing|Detection evidence)", l)]
        for s in stages[:16]:
            print("   ", s[:80])

        print("\n=== 5-7. map + starting point ===")
        for ln in t.splitlines():
            if re.search(r"STARTING_POINT|Latitude|Longitude|LAND MASK|Source|Contract|"
                         r"outside|No geographic", ln, re.I):
                print("   ", ln.strip()[:95])
        sp_card = page.locator('section:has(h3:text-is("Starting point"))').first
        if sp_card.count():
            print("   STARTING POINT CARD:", sp_card.inner_text().replace(chr(10), " | ")[:210])
        print("   leaflet tiles rendered:", page.locator("img.leaflet-tile").count())
        print("   leaflet vector layers :", page.locator(".leaflet-overlay-pane path").count())
        print("   OSM attribution       :", page.locator(".leaflet-control-attribution").count() > 0)

        print("\n=== 10-13. evidence / validity / recommendation / alert ===")
        for ln in t.splitlines():
            if re.search(r"Classification|Confidence|OOD risk|Top hypothesis|Posterior|"
                         r"uncalibrated|Top posterior|State$|Operational action|"
                         r"validity|valid$|Event|created|acknowledged", ln, re.I):
                print("   ", ln.strip()[:95])

        print("\n=== 14. acknowledge alert ===")
        ack = page.get_by_role("button", name=re.compile("Acknowledge alert", re.I))
        if ack.count() and ack.first.is_enabled():
            ack.first.click(); page.wait_for_timeout(2500)
            for ln in body().splitlines():
                if "confirmed by backend" in ln or "NOT AUTH" in ln:
                    print("   ->", ln.strip()[:95])
        else:
            print("   acknowledge unavailable (alert not in CREATED state)")

        print("\n=== 15. authorize mission ===")
        auth = page.get_by_role("button", name=re.compile("Authorize mission", re.I))
        print("   authorize button count:", auth.count())
        if auth.count():
            auth.first.click(); page.wait_for_timeout(3000)
            mcard = page.locator('section:has(h3:text-is("Mission"))').first
            if mcard.count():
                print("   MISSION CARD:", mcard.inner_text().replace(chr(10)," | ")[:180])
            for ln in body().splitlines():
                if "confirmed by backend" in ln or "NOT AUTH" in ln or "Mission authorized" in ln:
                    print("   ->", ln.strip()[:95])
        else:
            print("   no mission action available")

        print("\n=== 16. PRAMAN ===")
        for ln in body().splitlines():
            if re.search(r"Artifacts|Run |Actor|Generated|Case ", ln):
                print("   ", ln.strip()[:80])

        print("\n=== 17-18. logout, login as analyst ===")
        page.locator('header button[aria-haspopup="menu"]').first.click()
        page.wait_for_timeout(500)
        page.locator('header button:has-text("Log Out")').first.click(); page.wait_for_timeout(1200)
        print("   after logout:",
              page.locator('header button[aria-haspopup="menu"]').first.inner_text().replace("\n"," | "))
        print("   analyst     :", sign_in("analyst", "analyst-demo-pass"))

        print("\n=== 19-20. CASE-OOD fail-closed ===")
        page.get_by_role("button", name="CASE-OOD", exact=True).first.click()
        page.wait_for_timeout(2500)
        page.get_by_role("button", name=re.compile("Run VARUNA", re.I)).first.click()
        page.wait_for_timeout(6000)
        ood = body()
        for ln in ood.splitlines():
            if re.search(r"STARTING_POINT_UNAVAILABLE|UNAVAILABLE|No geographic|No alert|"
                         r"No mission|not produced|blocked|unavailable", ln, re.I):
                print("   ", ln.strip()[:100])

        print("\n=== network: failed requests ===")
        print("   ", failed_requests or "NONE")
        non200 = [c for c in calls if not c.startswith("200")]
        print("=== non-200 /v1/ responses ===")
        print("   ", non200 or "NONE")
        print("=== console errors (unique) ===")
        for c in sorted({re.sub(r'\s+', ' ', c)[:110] for c in console_errors}):
            print("   ", c)

        page.screenshot(path="reports/product/cockpit.png", full_page=False)
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
