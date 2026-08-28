#!/usr/bin/env python3
"""
Capture Liberty (Wentzville) boys soccer rows from MSHSAA.

    scrape_mshsaa.py <outdir>

Writes <outdir>/fr.txt and <outdir>/jv.txt, one row per line.

The page holds every level in a single table.schedule and only toggles row
visibility, so reading page text returns Varsity no matter which tab is
selected. Each level must be clicked, then only VISIBLE rows read. After
clicking we re-read the active tab label and refuse to save rows captured
under the wrong one -- a mismatched postback is the failure mode that would
otherwise silently overwrite one level's schedule with another's.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://www.mshsaa.org/MySchool/Schedule.aspx?s=965&alg=33"

LEVELS = {"fr": "Freshman", "jv": "Junior Varsity"}
EXPECTED = {"fr": 14, "jv": 17}
MIN_ROWS = 5
ATTEMPTS = 3

EXTRACT = """
async (LEVEL) => {
  function vis(el){ const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.offsetParent !== null; }
  const sp = [...document.querySelectorAll('#LevelsOfPlay span')]
    .find(e => e.textContent.trim() === LEVEL && e.className.includes('d-none'));
  if (!sp) return {error: 'no tab found for ' + LEVEL};
  sp.closest('a').click();
  await new Promise(r => setTimeout(r, 6000));
  const current = [...document.querySelectorAll('#LevelsOfPlay li.current')]
    .map(li => li.textContent.trim().split('\\n')[0].trim()).join(',');
  const t = document.querySelector('table.schedule');
  if (!t) return {error: 'table.schedule missing'};
  const rows = [...t.querySelectorAll('tr')].filter(vis)
    .map(tr => tr.innerText.replace(/\\s+/g, ' ').trim())
    .filter(x => /^\\d{1,2}\\/\\d{1,2}/.test(x));
  return {current, count: rows.length, rows};
}
"""


def capture(page, key):
    level = LEVELS[key]
    for attempt in range(1, ATTEMPTS + 1):
        result = page.evaluate(EXTRACT, level)
        if result.get("error"):
            print("  attempt %d: %s" % (attempt, result["error"]), file=sys.stderr)
            continue

        current, rows = result.get("current", ""), result.get("rows", [])
        if current != level:
            print(
                "  attempt %d: postback landed on %r, wanted %r" % (attempt, current, level),
                file=sys.stderr,
            )
            time.sleep(3)
            continue
        if len(rows) < MIN_ROWS:
            print(
                "  attempt %d: only %d rows under %s, re-reading" % (attempt, len(rows), level),
                file=sys.stderr,
            )
            time.sleep(3)
            continue

        expected = EXPECTED[key]
        note = "" if len(rows) == expected else "  (expected %d - schedule may have changed)" % expected
        print("  %s: %d rows%s" % (level, len(rows), note))
        return rows

    raise SystemExit("FAILED: could not read %s after %d attempts" % (level, ATTEMPTS))


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: scrape_mshsaa.py <outdir>")
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)

    captured = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )
        page = ctx.new_page()
        response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        if response is None or response.status >= 400:
            raise SystemExit(
                "FAILED: MSHSAA returned %s" % (response.status if response else "no response")
            )
        page.wait_for_selector("table.schedule", timeout=30000)
        page.wait_for_timeout(2000)

        for key in LEVELS:
            captured[key] = capture(page, key)

        browser.close()

    # Only write once both levels are captured cleanly, so a mid-run failure
    # never leaves one level updated and the other stale.
    for key, rows in captured.items():
        path = os.path.join(outdir, "%s.txt" % key)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(rows) + "\n")
        print("wrote %s (%d rows)" % (path, len(rows)))


if __name__ == "__main__":
    main()
