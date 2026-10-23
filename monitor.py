#!/usr/bin/env python3
"""Polite monitor for actual bookable NID appointment times at the Iraqi Consulate in Frankfurt.

It only reads public availability endpoints and sends Telegram alerts. It never books.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

BASE = "https://mofa.neetocal.com/api/v1/public/slots/12220"
FIRST_DATE_URL = BASE + "/first_available_date"
BOOKING_URL = "https://icass.mofa.gov.iq/#/booking"
TZ = "Europe/Berlin"
STATE_PATH = Path("monitor-state.json")
TIME_RE = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?!\d)")
DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NID-Appointment-Availability-Monitor/1.0 (personal low-frequency monitor)",
}


def get_json(url: str, params: dict | None = None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def find_dates(value) -> list[str]:
    found: set[str] = set()
    def walk(obj):
        if isinstance(obj, str):
            found.update(DATE_RE.findall(obj))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str):
                    found.update(DATE_RE.findall(k))
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
    walk(value)
    return sorted(d for d in found if valid_date(d))


def valid_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def extract_actual_times(payload) -> list[str]:
    """Extract only explicit time-bearing slot entries; dates without times do not count."""
    candidates: set[str] = set()

    def walk(obj, in_slots=False):
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_l = str(key).lower()
                if key_l in {"start", "start_time", "starttime", "time", "datetime", "date_time", "starts_at", "start_at"}:
                    if isinstance(value, str):
                        m = TIME_RE.search(value)
                        if m:
                            candidates.add(value.strip())
                # Common NeetoCal slot shapes include a "slots" object with time-keyed entries.
                if key_l == "slots":
                    walk(value, True)
                elif in_slots:
                    if isinstance(key, str) and TIME_RE.fullmatch(key.strip()):
                        candidates.add(key.strip())
                    walk(value, True)
                else:
                    walk(value, False)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and in_slots and TIME_RE.fullmatch(item.strip()):
                    candidates.add(item.strip())
                else:
                    walk(item, in_slots)
        elif isinstance(obj, str) and in_slots:
            if TIME_RE.fullmatch(obj.strip()):
                candidates.add(obj.strip())

    walk(payload)
    return sorted(candidates)


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID repository secrets.")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError("Telegram API rejected the message.")


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_signature": ""}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = datetime.now(ZoneInfo(TZ))
    # NeetoCal's first-available endpoint keeps this to one discovery request per run.
    first_payload = get_json(FIRST_DATE_URL, {"is_template": "false"})
    dates = find_dates(first_payload)
    if not dates:
        print("No first-available date reported.")
        return 0

    # The first-available endpoint may include unrelated timestamps; use the earliest future date.
    today = now.date().isoformat()
    future_dates = [d for d in dates if d >= today]
    if not future_dates:
        print("No future first-available date reported.")
        return 0

    first_date = future_dates[0]
    year, month, _ = first_date.split("-")
    params = {
        "year": year,
        "month": str(int(month)),
        "time_zone": TZ,
        "troubleshoot": "false",
        "override": "false",
        "duration": "5",
        "is_template": "false",
    }
    slots_payload = get_json(BASE, params)
    times = extract_actual_times(slots_payload)

    if not times:
        print(f"First available date endpoint returned {first_date}, but no explicit times were found in the month response.")
        # Do not alert based on dates alone: only real times count as bookable.
        return 0

    signature = json.dumps({"date": first_date, "times": times}, sort_keys=True)
    state = load_state()
    if signature == state.get("last_signature"):
        print("Availability unchanged; no notification.")
        return 0

    msg = (
        "🔔 Possible NID appointment availability detected\n"
        f"First available date: {first_date}\n"
        f"Times found: {', '.join(times[:20])}\n"
        "Open the official booking page and complete the booking manually:\n"
        f"{BOOKING_URL}\n\n"
        "Please verify the date/time on the official page; this monitor does not book appointments."
    )
    send_telegram(msg)
    state["last_signature"] = signature
    state["last_notified_at"] = now.isoformat()
    save_state(state)
    print("Telegram notification sent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        print(f"Availability endpoint returned HTTP error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Monitor error: {exc}", file=sys.stderr)
        raise SystemExit(1)
