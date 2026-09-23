#!/usr/bin/env python3
"""Print who is on-call right now for every schedule.

During business hours every after-hours schedule should show "nobody".
Run it once inside and once outside business hours to verify your setup.

Usage:
    python scripts/who_is_on_call.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oncall_api import OnCall  # noqa: E402


def main():
    api = OnCall()
    names = {}
    for schedule in api.list_all("schedules"):
        people = []
        for uid in schedule.get("on_call_now", []):
            if uid not in names:
                names[uid] = api.get(f"users/{uid}").get("username", uid)
            people.append(names[uid])
        print(f"{schedule['name']:<35} {', '.join(people) or 'nobody (paging off)'}")


if __name__ == "__main__":
    main()
