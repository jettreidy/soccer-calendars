#!/usr/bin/env python3
"""
Build a subscribable .ics from raw MSHSAA schedule rows.

    generate_ics.py <raw.txt> <fr|jv> <out.ics>

Exits non-zero (leaving the output untouched) when:
  * fewer than MIN_GAMES rows parsed as games
  * an away game names a venue with no address in ADDRESSES
  * a row contains a clock time that failed to parse as a game

UIDs are keyed on level + date + opponent slug and DTSTAMP is frozen, so
regenerating an unchanged schedule reproduces the file byte for byte.
Subscribers only ever see churn when the schedule itself changed.
"""

import os
import re
import sys
from datetime import date, datetime, timedelta

MIN_GAMES = 5
DTSTAMP = "20260101T000000Z"
TZID = "America/Chicago"
TEAM = "Liberty (Wentzville) Boys Soccer"

HOME_VENUE = "Liberty High School, 2275 Sommers Rd, O'Fallon, MO 63367"

LEVELS = {
    "fr": {"label": "Fr", "minutes": 60},
    "jv": {"label": "JV", "minutes": 90},
}

# Away venues. Keyed on the opponent name exactly as MSHSAA prints it.
ADDRESSES = {
    "Chaminade College Prep": "Chaminade College Preparatory School, 425 S Lindbergh Blvd, St. Louis, MO 63131",
    "Christian Brothers College": "Christian Brothers College High School, 1850 De La Salle Dr, Town and Country, MO 63017",
    "De Smet Jesuit": "De Smet Jesuit High School, 233 N New Ballas Rd, Creve Coeur, MO 63141",
    "Francis Howell": "Francis Howell High School, 7001 MO-94, St Charles, MO 63304",
    "Francis Howell Central": "Francis Howell Central High School, 5199 State Rte N, Cottleville, MO 63304",
    "Francis Howell North": "Francis Howell North High School, 2549 Hackmann Rd, St Charles, MO 63303",
    "Ft. Zumwalt East": "Fort Zumwalt East High School, 600 First Executive Ave, St Peters, MO 63376",
    "Ft. Zumwalt West": "Fort Zumwalt West High School, 1251 Turtle Creek Dr, O'Fallon, MO 63366",
    "Hazelwood West": "Hazelwood West High School, 1 Wildcat Lane, Hazelwood, MO 63042",
    "Helias Catholic": "Helias Catholic High School, 1305 Swifts Hwy, Jefferson City, MO 65109",
    "Kirkwood": "Kirkwood High School, 800 Dougherty Ferry Rd, Kirkwood, MO 63122",
    "Marquette": "Marquette High School, 2351 Clarkson Rd, Chesterfield, MO 63017",
    "Northwest (Cedar Hill)": "Northwest High School, 6005 Cedar Hill Rd, Cedar Hill, MO 63016",
    "Oakville": "Oakville High School, 5557 Milburn Rd, Oakville, MO 63129",
    "Parkway South": "Parkway South High School, 801 Hanna Rd, Manchester, MO 63021",
    "Quincy": "Quincy Senior High School, 3322 Maine St, Quincy, IL 62301",
    "Rock Bridge": "Rock Bridge High School, 4303 S Providence Rd, Columbia, MO 65203",
    "Timberland": "Timberland High School, 559 E Hwy N, Wentzville, MO 63385",
    "Troy Buchanan": "Troy Buchanan High School, 1190 Old Cap Au Gris Rd, Troy, MO 63379",
    "Warrenton": "Warren County R-3 Warrenton High School, 803 Pinckney, Warrenton, MO 63383",
}

ROW_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:-(\d{1,2}))?\s+(.*)$")
TIME_RE = re.compile(r"\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?$", re.I)
CITY_RE = re.compile(r"\s+([A-Z][A-Za-z.'\- ]*,\s*[A-Z]{2})$")
# MSHSAA appends a W-L or W-L-T record after a game is played: "(1-0)", "(0-0-1)".
# City qualifiers like "(Cedar Hill)" stay; only hyphenated integers are a record.
RECORD_RE = re.compile(r"\s+\(\d+-\d+(?:-\d+)?\)$")
CLOCK_RE = re.compile(r"\d{1,2}:\d{2}")


def fail(msg):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(1)


def season_year():
    """Season spans Aug-Nov. Override with SEASON_YEAR for a rebuild of a past season."""
    override = os.environ.get("SEASON_YEAR")
    if override:
        return int(override)
    today = date.today()
    return today.year if today.month >= 6 else today.year - 1


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return s.strip("-")


def esc(text):
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def parse_row(line, year):
    """Return a dict describing one row, or None if it is not a schedule row."""
    raw = re.sub(r"\s+Matchup$", "", line.strip()).strip()
    if not raw:
        return None

    m = ROW_RE.match(raw)
    if not m:
        return None

    month, day, end_day, rest = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4).strip()
    yr = year if month >= 6 else year + 1
    start = date(yr, month, day)

    tm = TIME_RE.search(rest)
    if tm:
        hour, minute, mer = int(tm.group(1)), int(tm.group(2)), tm.group(3).lower()
        if hour == 12:
            hour = 0
        if mer == "p":
            hour += 12
        rest = rest[: tm.start()].strip()
        start_dt = datetime(yr, month, day, hour, minute)
    else:
        # No published time. Emit an all-day block instead of guessing.
        if CLOCK_RE.search(rest):
            fail("row has a clock time that did not parse as a game: %r" % line.strip())
        start_dt = None

    away = False
    if rest.lower().startswith("at "):
        away = True
        rest = rest[3:].strip()

    # Strip a trailing record before the city suffix so "Quincy Quincy, IL (1-0)"
    # still yields opponent "Quincy". Do not touch "(Cedar Hill)"-style qualifiers.
    rest = RECORD_RE.sub("", rest).strip()

    # MSHSAA appends "City, ST" for out-of-area venues: "Quincy Quincy, IL".
    cm = CITY_RE.search(rest)
    if cm and start_dt is not None:
        rest = rest[: cm.start()].strip()

    opponent = rest.strip()
    if not opponent:
        fail("could not read an opponent from row: %r" % line.strip())

    end_date = None
    if end_day:
        end_date = date(yr, month, int(end_day))

    return {
        "date": start,
        "end_date": end_date,
        "start_dt": start_dt,
        "away": away,
        "opponent": opponent,
    }


def build_event(ev, level):
    label = LEVELS[level]["label"]
    minutes = LEVELS[level]["minutes"]
    uid = "lhs-%s-%s-%s@mshsaa" % (level, ev["date"].strftime("%Y%m%d"), slug(ev["opponent"]))

    out = ["BEGIN:VEVENT", "UID:%s" % uid, "DTSTAMP:%s" % DTSTAMP]

    if ev["start_dt"] is None:
        # Untimed tournament block -> all-day, DTEND exclusive.
        last = ev["end_date"] or ev["date"]
        out.append("SUMMARY:%s %s (%s) - time TBD" % (TEAM, ev["opponent"], label))
        out.append("DTSTART;VALUE=DATE:%s" % ev["date"].strftime("%Y%m%d"))
        out.append("DTEND;VALUE=DATE:%s" % (last + timedelta(days=1)).strftime("%Y%m%d"))
        out.append(
            "DESCRIPTION:%s boys soccer. %s. Start time not yet published by MSHSAA."
            % (label, ev["opponent"])
        )
        out.append("END:VEVENT")
        return out

    end_dt = ev["start_dt"] + timedelta(minutes=minutes)
    if ev["away"]:
        venue = ADDRESSES.get(ev["opponent"])
        if not venue:
            fail(
                "venue with no known address: %r. Add a street address to the "
                "ADDRESSES map in tools/generate_ics.py before it can flow through."
                % ev["opponent"]
            )
        out.append("SUMMARY:%s Away Game at %s (%s)" % (TEAM, ev["opponent"], label))
    else:
        venue = HOME_VENUE
        out.append("SUMMARY:%s Home Game vs. %s (%s)" % (TEAM, ev["opponent"], label))

    out.append("DTSTART;TZID=%s:%s" % (TZID, ev["start_dt"].strftime("%Y%m%dT%H%M%S")))
    out.append("DTEND;TZID=%s:%s" % (TZID, end_dt.strftime("%Y%m%dT%H%M%S")))
    out.append("LOCATION:%s" % esc(venue))
    out.append(
        "DESCRIPTION:%s boys soccer. %s %s."
        % (label, "Away at" if ev["away"] else "Home vs.", ev["opponent"])
    )
    out.append("END:VEVENT")
    return out


def main():
    if len(sys.argv) != 4:
        fail("usage: generate_ics.py <raw.txt> <fr|jv> <out.ics>")

    src, level, dest = sys.argv[1], sys.argv[2], sys.argv[3]
    if level not in LEVELS:
        fail("level must be one of: %s" % ", ".join(LEVELS))

    year = season_year()
    with open(src, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]

    events = [e for e in (parse_row(ln, year) for ln in lines) if e]
    if len(events) < MIN_GAMES:
        fail("parsed only %d games from %s (minimum %d)" % (len(events), src, MIN_GAMES))

    label = LEVELS[level]["label"]
    body = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Liberty Wentzville Boys Soccer//%s//EN" % label,
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:%s %s" % (TEAM, label),
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
        "BEGIN:VTIMEZONE",
        "TZID:%s" % TZID,
        "BEGIN:STANDARD",
        "DTSTART:20071104T020000",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0600",
        "TZNAME:CST",
        "END:STANDARD",
        "BEGIN:DAYLIGHT",
        "DTSTART:20070311T020000",
        "TZOFFSETFROM:-0600",
        "TZOFFSETTO:-0500",
        "TZNAME:CDT",
        "END:DAYLIGHT",
        "END:VTIMEZONE",
    ]
    for ev in events:
        body.extend(build_event(ev, level))
    body.append("END:VCALENDAR")

    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")

    print("%s: %d events -> %s" % (level, len(events), dest))


if __name__ == "__main__":
    main()
