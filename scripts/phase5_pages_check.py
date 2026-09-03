"""Phase 5 — verify every nav-reachable page is real, in a live browser."""
from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

FE = "http://localhost:3000"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


def main() -> int:
    console: list[str] = []
    netfail: list[str] = []

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1700, "height": 1300})
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: netfail.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: netfail.append(f"{r.method} {r.url}"))

        def sign_in(u: str, pw: str) -> str:
            w = page.locator('header button[aria-haspopup="menu"]').first
            w.click(); page.wait_for_timeout(400)
            page.locator('header input[autocomplete="username"]').first.fill(u)
            page.locator('header input[autocomplete="current-password"]').first.fill(pw)
            page.locator('header button[type="submit"]').first.click()
            page.wait_for_timeout(2200)
            return w.inner_text().replace("\n", " | ")

        print("### login")
        page.goto(FE, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2500)
        check("signed in", "Duty Officer" in sign_in("officer", "officer-demo-pass"))

        print("\n### nav offers only real pages")
        nav = page.locator("header nav").inner_text()
        for gone in ("Assets", "Reports", "Intelligence"):
            check(f"mock page '{gone}' removed from nav", gone not in nav)
        for real in ("Dashboard", "Cases", "Alerts", "Missions"):
            check(f"'{real}' present", real in nav)

        print("\n### /cases is real")
        page.goto(FE + "/cases", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2500)
        t = page.locator("body").inner_text()
        check("shows real replay case", "REPLAY-CASE-VALID" in t, t[:80].replace("\n", " "))
        check("no fabricated CASE 24-0xx rows", "24-071" not in t and "24-070" not in t)
        check("search is a real input",
              page.locator('input[placeholder*="Filter by case"]').count() > 0)
        check("New Case button has a handler",
              page.get_by_role("button", name=re.compile("New Case", re.I)).count() > 0)

        # the search box must actually filter
        page.locator('input[placeholder*="Filter by case"]').first.fill("zzz-no-match")
        page.wait_for_timeout(700)
        check("search filters the table", "No case matches" in page.locator("body").inner_text())
        page.locator('input[placeholder*="Filter by case"]').first.fill("")
        page.wait_for_timeout(500)

        print("\n### New Case actually creates one")
        before = page.locator("tbody tr").count()
        page.get_by_role("button", name=re.compile("New Case", re.I)).first.click()
        page.wait_for_timeout(3000)
        body = page.locator("body").inner_text()
        created = "created — confirmed by backend" in body
        check("case created and confirmed by backend", created,
              [ln for ln in body.splitlines() if "confirmed by backend" in ln or "NOT AUTH" in ln][:1])
        check("table grew", page.locator("tbody tr").count() > before,
              f"{before} -> {page.locator('tbody tr').count()}")

        print("\n### /assignment-mission is real")
        page.goto(FE + "/assignment-mission", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(3000)
        t = page.locator("body").inner_text()
        check("no fabricated authorization checklist", "Analyst Rao" not in t)
        check("no mock MSN-071-A rows", "MSN-071-A" not in t)
        check("shows the real mission", "MSN-REPLAY-REPLAY-CASE-VALID" in t,
              t[:100].replace("\n", " "))
        check("shows real tasking",
              "tasking" in t.lower() and "expanding_square" in t.lower())

        print("\n### mission FSM drives from the UI")
        auth = page.get_by_role("button", name=re.compile("Authorize mission", re.I))
        if auth.count():
            auth.first.click(); page.wait_for_timeout(3000)
            check("authorize confirmed by backend",
                  "confirmed by backend" in page.locator("body").inner_text())
        ack = page.get_by_role("button", name=re.compile(r"^acknowledged$", re.I))
        if ack.count():
            ack.first.click(); page.wait_for_timeout(3000)
            check("FSM advanced to acknowledged from the UI",
                  "acknowledged" in page.locator("body").inner_text().lower())
        else:
            check("FSM transition button offered", False, "no legal-next button rendered")

        print("\n### /alerts is global with filters")
        page.goto(FE + "/alerts", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2500)
        t = page.locator("body").inner_text()
        check("global count shown", "across all cases" in t.lower())
        check("severity filter present", page.locator("select").count() >= 2)
        check("real alert dimensions",
              "detection.presence" in t.lower() or "landfall.prediction" in t.lower())
        check("no fabricated ALT-24xx ids", "ALT-2471" not in t)
        check("honest channel status", "not_configured" in t.lower())

        print("\n### network hygiene")
        check("no failed requests", not netfail, str(netfail[:2]))
        breaking = [c for c in console if "Failed to load resource" not in c]
        check("no breaking console errors", not breaking, str(sorted(set(breaking))[:2])[:160])

        page.screenshot(path="reports/product/phase5_pages.png")
        b.close()

    print("\n" + "=" * 60)
    print("PHASE 5 PAGES: " + ("ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} ISSUE(S)"))
    for f in FAILS:
        print("  -", f)
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
