"""Dump the visible operator-facing text of the running frontend, so we can
see exactly what a human sees (including any 'unavailable' states) rather
than inferring it from the API payload."""
from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3000"


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(FRONTEND + target, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        body = page.locator("body").inner_text()
        body = re.sub(r"\n{3,}", "\n\n", body)
        print(f"===== VISIBLE TEXT {target} =====")
        print(body)

        print("\n===== 'unavailable'/'not produced' lines =====")
        for line in body.splitlines():
            if re.search(r"unavail|not[ _]yet|not produced|blocked|NOT AUTH", line, re.I):
                print("  ", line.strip())

        if errors:
            print("\n===== page errors =====")
            for e in errors:
                print("  ", e)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
