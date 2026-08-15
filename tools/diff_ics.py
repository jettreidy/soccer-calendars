#!/usr/bin/env python3
"""
Classify the change between two generated .ics files.

    diff_ics.py <previous.ics> <current.ics>

Exit codes drive the caller; do not interpret the git diff by hand.

  0  NO CHANGES
  1  real change. One line per change on stdout:
       ADDED / REMOVED / TIME CHANGED / LOCATION CHANGED / TITLE CHANGED
     A game moving to a new date shows as REMOVED plus ADDED, because event
     IDs are keyed on date. That is correct, not a bug.
  2  SUSPICIOUS. Looks like a parser break rather than a schedule edit:
     most events vanished, many lost their locations, or many timed games
     silently became all-day. Caller must restore and not commit.
"""

import re
import sys
from datetime import datetime

# Below these, a proportional test is meaningless, so require an absolute count.
SUSPICIOUS_MIN_COUNT = 3
SUSPICIOUS_FRACTION = 0.30
VANISHED_FRACTION = 0.50


def parse(path):
    events, cur = {}, None
    with open(path, encoding="utf-8") as fh:
        for line in fh.read().splitlines():
            if line == "BEGIN:VEVENT":
                cur = {}
            elif line == "END:VEVENT":
                if cur is not None and "uid" in cur:
                    events[cur["uid"]] = cur
                cur = None
            elif cur is not None:
                if line.startswith("UID:"):
                    cur["uid"] = line[4:]
                elif line.startswith("SUMMARY:"):
                    cur["summary"] = line[8:]
                elif line.startswith("LOCATION:"):
                    cur["location"] = line[9:]
                elif line.startswith("DTSTART"):
                    cur["dtstart"] = line.split(":", 1)[1]
                    cur["allday"] = "VALUE=DATE" in line
    return events


def describe(ev):
    """A short human label: '10/15 at Warrenton, 5:00pm'."""
    raw = ev.get("dtstart", "")
    when, clock = "?", None
    try:
        if ev.get("allday"):
            when = datetime.strptime(raw, "%Y%m%d").strftime("%-m/%-d")
        else:
            dt = datetime.strptime(raw, "%Y%m%dT%H%M%S")
            when = dt.strftime("%-m/%-d")
            clock = dt.strftime("%-I:%M%p").lower()
    except ValueError:
        pass

    summary = ev.get("summary", "")
    m = re.search(r"(?:Away Game (at)|Home Game (vs\.)) (.+?) \((?:Fr|JV)\)", summary)
    if m:
        who = "%s %s" % (m.group(1) or m.group(2), m.group(3))
    else:
        m = re.search(r"Boys Soccer (.+?) \((?:Fr|JV)\)", summary)
        who = m.group(1) if m else summary

    return "%s %s%s" % (when, who, ", %s" % clock if clock else ", time TBD")


def main():
    if len(sys.argv) != 3:
        print("usage: diff_ics.py <previous.ics> <current.ics>", file=sys.stderr)
        return 2

    old, new = parse(sys.argv[1]), parse(sys.argv[2])
    added = [u for u in new if u not in old]
    removed = [u for u in old if u not in new]
    both = [u for u in old if u in new]

    lost_location = [u for u in both if old[u].get("location") and not new[u].get("location")]
    became_allday = [u for u in both if not old[u].get("allday") and new[u].get("allday")]

    def suspicious(hits, population):
        return len(hits) >= SUSPICIOUS_MIN_COUNT and len(hits) >= population * SUSPICIOUS_FRACTION

    reasons = []
    if old and len(removed) >= max(SUSPICIOUS_MIN_COUNT, len(old) * VANISHED_FRACTION):
        reasons.append("%d of %d events vanished" % (len(removed), len(old)))
    if suspicious(lost_location, len([u for u in both if old[u].get("location")])):
        reasons.append("%d events lost their location" % len(lost_location))
    if suspicious(became_allday, len(both)):
        reasons.append("%d timed games became all-day" % len(became_allday))

    if reasons:
        print("SUSPICIOUS: " + "; ".join(reasons))
        for u in removed:
            print("  would have REMOVED %s" % describe(old[u]))
        for u in lost_location:
            print("  would have LOST LOCATION %s" % describe(new[u]))
        for u in became_allday:
            print("  would have BECOME ALL-DAY %s" % describe(new[u]))
        return 2

    lines = []
    for u in added:
        lines.append("ADDED %s" % describe(new[u]))
    for u in removed:
        lines.append("REMOVED %s" % describe(old[u]))
    for u in both:
        if old[u].get("dtstart") != new[u].get("dtstart"):
            lines.append(
                "TIME CHANGED %s (was %s)" % (describe(new[u]), describe(old[u]))
            )
        if old[u].get("location") != new[u].get("location"):
            lines.append("LOCATION CHANGED %s" % describe(new[u]))
        if old[u].get("summary") != new[u].get("summary"):
            lines.append("TITLE CHANGED %s" % describe(new[u]))

    if not lines:
        return 0

    for line in lines:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
