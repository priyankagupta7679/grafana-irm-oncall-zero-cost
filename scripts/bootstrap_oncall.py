#!/usr/bin/env python3
"""Build a zero-cost, after-hours-only on-call setup in Grafana IRM.

Creates (idempotently, matched by name):
  * one calendar schedule per tier, containing only AFTER-HOURS shifts
  * an optional "all tiers" schedule for the final page-everyone step
  * one escalation chain per environment:
        wait -> tier1 -> wait -> tier2 -> ... -> everyone
  * integrations (Alertmanager / SNS / webhook ...) and regex routes
  * Teams outgoing webhooks (FIRING + RESOLVED), which run 24x7

During business hours nobody is on shift, so the "notify on-call from
schedule" steps find no one and are skipped: Teams gets the alert, phones
stay quiet. After hours, the IRM mobile app pages the on-call person.

Usage:
    python scripts/bootstrap_oncall.py --config config.yaml --dry-run
    python scripts/bootstrap_oncall.py --config config.yaml
"""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oncall_api import REPO_ROOT, OnCall, load_dotenv  # noqa: E402

DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
FREE_TIER_IRM_USERS = 3  # Grafana Cloud Free: active IRM users per month


def minutes(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def after_hours_windows(business):
    """Return [(start_day, start_hhmm, duration_seconds)] covering every
    minute of the week that is NOT business hours.

    Each window starts when a business day ends and runs until the next
    business day starts, so Friday evening -> Monday morning is one window.
    """
    start, end = minutes(business["start"]), minutes(business["end"])
    if end <= start:
        sys.exit("ERROR: business_hours.end must be after business_hours.start")
    days = [d for d in DAYS if d in business["days"]]
    if not days:
        sys.exit("ERROR: business_hours.days is empty")
    windows = []
    for i, day in enumerate(days):
        today = DAYS.index(day)
        nxt = DAYS.index(days[(i + 1) % len(days)])
        gap_days = (nxt - today) % 7 or 7
        duration_min = gap_days * 1440 - (end - start)
        windows.append((day, business["end"], duration_min * 60))
    return windows


def group_windows(windows):
    """Merge days that share the same window length into one weekly shift."""
    groups = {}
    for day, start, duration in windows:
        groups.setdefault((start, duration), []).append(day)
    return [(days, start, duration) for (start, duration), days in groups.items()]


def first_date_on_or_after(date, day_code):
    target = DAYS.index(day_code)
    return date + dt.timedelta(days=(target - date.weekday()) % 7)


class Builder:
    def __init__(self, api, cfg, dry_run):
        self.api, self.cfg, self.dry = api, cfg, dry_run
        self.tz = cfg["timezone"]

    def ensure(self, path, name, body, **find_params):
        existing = self.api.find_by_name(path, name, **find_params) if self.api else None
        if existing:
            print(f"  = exists   {path}: {name}")
            return existing
        print(f"  + create   {path}: {name}")
        if self.dry:
            return {"id": f"<dry-run:{name}>", "link": "<dry-run>"}
        return self.api.post(path, body)

    def build_schedule(self, name, user_ids):
        """Calendar schedule made of after-hours shifts for the given users.
        All users in the list are on-call at the same time."""
        shift_ids = []
        start_date = dt.date.fromisoformat(str(self.cfg["rotation_start_date"]))
        for days, start, duration in group_windows(after_hours_windows(self.cfg["business_hours"])):
            first = first_date_on_or_after(start_date, days[0])
            shift_name = f"{name}-{'-'.join(days)}"
            shift = self.ensure("on_call_shifts", shift_name, {
                "name": shift_name,
                "type": "rolling_users",
                "time_zone": self.tz,
                "start": f"{first.isoformat()}T{start}:00",
                "duration": duration,
                "frequency": "weekly",
                "interval": 1,
                "week_start": "MO",
                "by_day": days,
                # one inner list = everyone in it is on-call together
                "rolling_users": [user_ids],
                "start_rotation_from_user_index": 0,
            })
            shift_ids.append(shift["id"])
        return self.ensure("schedules", name, {
            "name": name,
            "type": "calendar",
            "time_zone": self.tz,
            "shifts": shift_ids,
        })

    def build_chain(self, env_name, tier_schedules, all_schedule):
        esc = self.cfg["escalation"]
        chain_name = f"{env_name}-after-hours"
        chain = self.ensure("escalation_chains", chain_name, {"name": chain_name})
        if not self.dry and self.api.list_all("escalation_policies", escalation_chain_id=chain["id"]):
            print(f"  = chain {chain_name} already has steps, leaving it untouched")
            return chain

        steps = [{"type": "wait", "duration": esc["first_wait_minutes"] * 60}]
        for i, sched in enumerate(tier_schedules):
            if i > 0:
                steps.append({"type": "wait", "duration": esc["wait_between_tiers_minutes"] * 60})
            steps.append({"type": "notify_on_call_from_schedule",
                          "notify_on_call_from_schedule": sched["id"], "important": True})
        if all_schedule:
            steps.append({"type": "wait", "duration": esc["wait_between_tiers_minutes"] * 60})
            steps.append({"type": "notify_on_call_from_schedule",
                          "notify_on_call_from_schedule": all_schedule["id"], "important": True})

        for pos, step in enumerate(steps):
            detail = f"{step['duration'] // 60} min" if step["type"] == "wait" else step["notify_on_call_from_schedule"]
            print(f"    step {pos}: {step['type']} ({detail})")
            if not self.dry:
                self.api.post("escalation_policies",
                              {**step, "escalation_chain_id": chain["id"], "position": pos})
        return chain

    def build_integrations(self, chains):
        links = {}
        first_chain = chains[self.cfg["environments"][0]["name"]]["id"]
        for integ in self.cfg["integrations"]:
            obj = self.ensure("integrations", integ["name"],
                              {"name": integ["name"], "type": integ["type"]})
            links[integ["name"]] = obj.get("link", "")
            if self.dry:
                for env in self.cfg["environments"]:
                    print(f"    route {env['routing_regex']} -> {env['name']}-after-hours")
                continue
            routes = self.api.list_all("routes", integration_id=obj["id"])
            existing_regex = {r.get("routing_regex") for r in routes}
            for pos, env in enumerate(self.cfg["environments"]):
                if env["routing_regex"] in existing_regex:
                    continue
                print(f"    route {env['routing_regex']} -> {env['name']}-after-hours")
                self.api.post("routes", {
                    "integration_id": obj["id"],
                    "escalation_chain_id": chains[env["name"]]["id"],
                    "routing_type": "regex",
                    "routing_regex": env["routing_regex"],
                    "position": pos,
                })
            # Default route catches anything no regex matched -> first environment
            default = next((r for r in routes if r.get("is_the_last_route")), None)
            if default and default.get("escalation_chain_id") != first_chain:
                self.api.put(f"routes/{default['id']}", {"escalation_chain_id": first_chain})
        return links

    def build_teams_webhooks(self):
        if not self.cfg.get("teams", {}).get("enabled"):
            return
        url = os.environ.get("TEAMS_WEBHOOK_URL", "")
        if not url or "replace-me" in url:
            print("  ! TEAMS_WEBHOOK_URL not set in .env, skipping Teams webhooks")
            return
        tpl_dir = REPO_ROOT / "templates"
        for name, trigger, tpl in [
            ("Teams-Firing", "alert group created", "teams-firing.json.j2"),
            ("Teams-Resolved", "resolve", "teams-resolved.json.j2"),
        ]:
            self.ensure("webhooks", name, {
                "name": name,
                "url": url,
                "http_method": "POST",
                "trigger_type": trigger,
                "is_webhook_enabled": True,
                # forward_all MUST be false, otherwise the raw payload is sent
                # instead of the card template and Teams rejects it
                "forward_all": False,
                "data": (tpl_dir / tpl).read_text(encoding="utf-8"),
            })


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    load_dotenv()

    if len(cfg["tiers"]) > FREE_TIER_IRM_USERS:
        print(f"WARNING: {len(cfg['tiers'])} tiers configured. Grafana Cloud Free includes "
              f"{FREE_TIER_IRM_USERS} active IRM users/month; anyone in a schedule or "
              "escalation chain counts. Extra users need the paid Pro plan.\n")

    print("After-hours windows (paging ON):")
    for days, start, duration in group_windows(after_hours_windows(cfg["business_hours"])):
        print(f"  {','.join(days)} from {start} for {duration / 3600:g}h ({cfg['timezone']})")

    api = None if args.dry_run else OnCall()
    b = Builder(api, cfg, args.dry_run)

    print("\nSchedules:")
    tier_ids = [api.user_id_by_email(t["email"]) if api else f"<{t['email']}>" for t in cfg["tiers"]]
    tier_schedules = [b.build_schedule(f"{t['name']}-after-hours", [uid])
                      for t, uid in zip(cfg["tiers"], tier_ids)]
    all_schedule = (b.build_schedule("all-tiers-after-hours", tier_ids)
                    if cfg["escalation"].get("page_everyone_at_end") else None)

    print("\nEscalation chains:")
    chains = {env["name"]: b.build_chain(env["name"], tier_schedules, all_schedule)
              for env in cfg["environments"]}

    print("\nIntegrations:")
    links = b.build_integrations(chains)

    print("\nTeams webhooks:")
    b.build_teams_webhooks()

    print("\nDone. Point your alert sources at these integration URLs.")
    print("Treat them like passwords: anyone with the URL can create alerts.")
    for name, link in links.items():
        print(f"  {name}: {link}")


if __name__ == "__main__":
    main()
