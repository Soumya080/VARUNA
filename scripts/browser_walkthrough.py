"""Full operator-session walkthrough against the RUNNING stack.

login -> dashboard -> alerts -> acknowledge -> missions -> logout,
capturing console errors, failed requests and every /v1/ call.
"""
from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

FE = "http://localhost:3000"


def main() -> int:
    console_errors: list[str] = []
    failures: list[str] = []
    calls: list[str] = []

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1600, "height": 1200})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: failures.append(f"pageerror: {e}"))
        page.on("requestfailed",
                lambda r: failures.append(f"requestfailed {r.method} {r.url} :: {r.failure}"))
        page.on("response",
                lambda r: calls.append(f"{r.status} {r.request.method} {r.url.split('8000')[-1]}")
                if "/v1/" in r.url else None)

        def login(user: str, pw: str) -> str:
            page.locator('header button[aria-haspopup="menu"]').first.click()
            page.wait_for_timeout(400)
            page.locator('header input[autocomplete="username"]').first.fill(user)
            page.locator('header input[autocomplete="current-password"]').first.fill(pw)
            page.locator('header button[type="submit"]').first.click()
            page.wait_for_timeout(2000)
            return page.locator('header button[aria-haspopup="menu"]').first.inner_text().replace("\n", " | ")

        print("=== 1. dashboard + login as officer ===")
        page.goto(FE, wait_until="networkidle", timeout=60000)
        print("  identity:", login("officer", "officer-demo-pass"))

        print("\n=== 2. alerts page ===")
        page.goto(FE + "/alerts", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)
        txt = page.locator("body").inner_text()
        for ln in txt.splitlines():
            if re.search(r"validity\.evaluated|mission\.assigned|created|acknowledged|escalated|resolved|WARNING|warning", ln):
                print("  ", ln.strip()[:110])

        print("\n=== 3. click an alert action ===")
        for label in ("Acknowledge", "Escalate", "Resolve"):
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0:
                btn.first.click()
                page.wait_for_timeout(1800)
                body = page.locator("body").inner_text()
                for ln in body.splitlines():
                    if "confirmed by backend" in ln or "NOT AUTH" in ln:
                        print(f"   {label} -> {ln.strip()[:100]}")
                break
        else:
            print("   no lifecycle action button available (alert already resolved)")

        print("\n=== 4. missions page ===")
        page.goto(FE + "/missions", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)
        mt = page.locator("body").inner_text()
        for ln in mt.splitlines():
            if re.search(r"MSN-|available|assigned|No live missions|Not yet approved", ln):
                print("  ", ln.strip()[:110])

        print("\n=== 5. logout ===")
        page.locator('header button[aria-haspopup="menu"]').first.click()
        page.wait_for_timeout(400)
        lo = page.get_by_role("button", name="Log Out")
        if lo.count():
            lo.first.click()
            page.wait_for_timeout(1000)
        print("  identity:",
              page.locator('header button[aria-haspopup="menu"]').first.inner_text().replace("\n", " | "))

        print("\n=== /v1/ calls ===")
        for c in calls:
            print("  ", c)
        print("\n=== console errors ===")
        uniq = sorted({re.sub(r"\s+", " ", c)[:120] for c in console_errors})
        for c in uniq:
            print("  ", c)
        print("\n=== failures ===")
        for f in failures:
            print("  ", f)
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
