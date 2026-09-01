# Liberty (Wentzville) boys soccer calendars

Subscription feeds for the 2026-2027 season. No login required - anyone with a link can subscribe.

## Freshman

https://raw.githubusercontent.com/jettreidy/soccer-calendars/main/calendars/fr.ics

13 games. All have published start times and venue addresses.

## Junior varsity

https://raw.githubusercontent.com/jettreidy/soccer-calendars/main/calendars/jv.ics

17 events: 14 games with times and addresses, plus three tournament blocks that MSHSAA has not yet assigned times to. Those appear as all-day events marked "time TBD" and will gain real times once the school publishes them.

## Subscribing

Apple Calendar (Mac): File > New Calendar Subscription, paste the URL, set Location to iCloud so it syncs to iPhone and iPad, and Auto-refresh to Every hour or Every 5 minutes.

Google Calendar: Other calendars > From URL.

Subscribed calendars are read-only on the client. Edits happen here.

## Source

Schedules come from the MSHSAA page for Liberty (Wentzville) boys soccer, levels Freshman and Junior Varsity: https://www.mshsaa.org/MySchool/Schedule.aspx?s=965&alg=33

Event UIDs are keyed on date plus opponent, so adding or removing a game affects only that event and leaves the rest of the season untouched for existing subscribers.

## How it stays current

The public subscribe URLs above stay the same. Both calendars are updated
daily from the MSHSAA schedule page: scrape, regenerate, and commit only when
something actually changed.

    tools/scrape_mshsaa.py   MSHSAA page -> raw/fr.txt, raw/jv.txt
    tools/generate_ics.py    raw rows    -> calendars/*.ics
    tools/diff_ics.py        classifies old vs new; exit 0 none / 1 change / 2 suspicious

Event UIDs are keyed on level, date, and opponent, and DTSTAMP is frozen, so
regenerating an unchanged schedule reproduces each file byte for byte. A commit
only ever appears when the schedule itself moved, and subscribers never see
events churn.

A degraded calendar is never published. The generator exits non-zero if it
parses fewer than 5 games, meets an away venue missing from its address map,
or sees a row with a clock time it could not read. The differ exits 2 if most
events vanished, many lost their locations, or many timed games became
all-day - a parser break rather than a schedule edit. Either case restores the
previous files and fails loudly.

### New opponents

An away game against a school not in the `ADDRESSES` map in
`tools/generate_ics.py` fails the run by design, naming the school. Add its
street address there and re-run; the address is what makes the calendar entry
open directions rather than a bare school name.
