"""
VARUNA runtime stabilization — real-browser walkthrough harness.

Not a test fixture: this drives the ACTUAL running frontend at
http://localhost:3000 against the ACTUAL running backend, captures console
errors and network failures, and reports exactly what a human operator
would see. Used to reproduce and then verify the auth/geospatial/loop
failures reported against the running product.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3000"
USERNAME = "officer"
PASSWORD = "officer-demo-pass"


def main() -> int:
    console: list[str] = []
    failures: list[str] = []
    requests: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: failures.append(f"[pageerror] {e}"))
        page.on("requestfailed",
                lambda r: failures.append(f"[requestfailed] {r.method} {r.url} :: {r.failure}"))
        page.on("response", lambda r: requests.append(f"{r.status} {r.request.method} {r.url}")
                if "/v1/" in r.url else None)

        print("=== 1. open dashboard ===")
        page.goto(FRONTEND, wait_until="networkidle", timeout=60000)
        print("title:", page.title())

        print("\n=== 2. open profile widget ===")
        # The widget is the only button with aria-haspopup=menu in the header
        widget = page.locator('header button[aria-haspopup="menu"]')
        print("widget count:", widget.count())
        print("widget text before:", widget.first.inner_text().replace("\n", " | "))
        widget.first.click()
        page.wait_for_timeout(500)

        print("\n=== 3. login form present? ===")
        user_input = page.locator('header input[autocomplete="username"]')
        pass_input = page.locator('header input[autocomplete="current-password"]')
        print("username input:", user_input.count(), "password input:", pass_input.count())

        if user_input.count() == 0:
            print("!! LOGIN FORM NOT FOUND")
            print("header html:\n", page.locator("header").inner_html()[:3000])
            browser.close()
            return 1

        print("\n=== 4. submit credentials ===")
        user_input.first.fill(USERNAME)
        pass_input.first.fill(PASSWORD)
        page.locator('header button[type="submit"]').first.click()
        page.wait_for_timeout(2500)

        print("widget text after:", widget.first.inner_text().replace("\n", " | "))
        header_txt = page.locator("header").inner_text()
        for marker in ("Invalid username or password", "Could not reach the backend",
                       "Duty Officer", "Not signed in"):
            if marker in header_txt:
                print(f"  MARKER PRESENT: {marker!r}")

        print("\n=== /v1/ requests seen ===")
        for r in requests:
            print(" ", r)

        print("\n=== console ===")
        for c in console[-25:]:
            print(" ", c)

        print("\n=== failures ===")
        for f in failures:
            print(" ", f)

        page.screenshot(path="reports/product/browser_login.png", full_page=False)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
