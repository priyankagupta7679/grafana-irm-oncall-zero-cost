#!/usr/bin/env python3
"""Pause or resume ALL phone paging in one command, without losing config.

  pause  : saves every route's escalation chain to backups/routes_<time>.json,
           then detaches the chains. Alerts still arrive and Teams webhooks
           still post; nobody's phone rings. Useful for maintenance windows,
           migrations, or billing problems on the account.
  resume : restores the exact chains from a backup file.

Usage:
    python scripts/paging_toggle.py pause
    python scripts/paging_toggle.py resume backups/routes_20260101T120000.json
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oncall_api import REPO_ROOT, OnCall  # noqa: E402


def pause(api):
    routes = api.list_all("routes")
    backup = [{"id": r["id"], "integration_id": r["integration_id"],
               "escalation_chain_id": r.get("escalation_chain_id")} for r in routes]
    out_dir = REPO_ROOT / "backups"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"routes_{dt.datetime.now():%Y%m%dT%H%M%S}.json"
    path.write_text(json.dumps(backup, indent=2), encoding="utf-8")
    print(f"Backed up {len(backup)} routes to {path}")

    for r in backup:
        if r["escalation_chain_id"]:
            api.put(f"routes/{r['id']}", {"escalation_chain_id": None})
            print(f"  paused route {r['id']}")
    print("Paging paused. Teams notifications continue.")


def resume(api, backup_file):
    backup = json.loads(Path(backup_file).read_text(encoding="utf-8"))
    for r in backup:
        if r["escalation_chain_id"]:
            api.put(f"routes/{r['id']}", {"escalation_chain_id": r["escalation_chain_id"]})
            print(f"  restored route {r['id']}")
    print("Paging resumed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["pause", "resume"])
    parser.add_argument("backup_file", nargs="?", help="required for resume")
    args = parser.parse_args()

    api = OnCall()
    if args.action == "pause":
        pause(api)
    elif not args.backup_file:
        sys.exit("ERROR: resume needs the backup file created by 'pause'")
    else:
        resume(api, args.backup_file)


if __name__ == "__main__":
    main()
