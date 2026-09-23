# Troubleshooting and lessons learned

Real problems hit while running this in production, and their fixes.

| Symptom | Cause | Fix |
|---|---|---|
| Every Teams channel receives every project's alerts | Outgoing webhooks had an empty **trigger template**, so they fire for all alert groups | Add `{{ 'app-a' in alert_group.title }}` (one per project) |
| Teams / Power Automate flow fails with 400/417, or shows a raw JSON blob | Webhook had **forward whole payload = ON**, so the card template was ignored | Turn it OFF so the `data` template is sent |
| The same alert appears twice in Teams | Two paths post to the same channel (e.g. an old IRM stack *and* a direct relay) | List every sender of that webhook URL. Disable, don't just "assume dead", the unused one |
| Nobody paged at night | Chain used *Notify users* on a schedule-less path, or the schedule has a gap | Use *Notify users from on-call schedule*; check the schedule preview for holes (Fri night, public holidays) |
| People paged during office hours | A *Notify users* (direct) step, or a 24x7 rotation left in the schedule | Only after-hours rotations in schedules; no direct-user steps |
| Phone doesn't ring when locked or silent | App lacks DND override / Critical Alerts, or battery optimisation kills it | See UI-SETUP A5 and send a test notification with the phone locked |
| New user gets "contact your org admin for an invite" | SSO doesn't auto-provision users | Admin invites them first, then they sign in with SSO |
| Unexpected bill / "active users" above 3 | Someone outside the rota acknowledged an alert or edited config | Keep IRM access to the 3 rota members; others watch Teams |
| Web-schedule shift can't be created via the public API | Rotations of UI (*web*) schedules are managed by the UI | The script uses **calendar** schedules + `on_call_shifts`, which the API fully supports |
| API returns 400 on a `wait` step | Some API versions only accept fixed wait durations | Use 1, 5, 15, 30 or 60 min in `config.yaml`, or edit the step in the UI |
| Alerts missing during an incident storm | Ingestion limit of 300 alerts per 5 min per integration (900 per org) | Group alerts at the source (Alertmanager `group_by`), send only critical |
| Zabbix media type "works" but nothing arrives | Media type had **no message templates**, so Zabbix silently skips it | Add Problem + Recovery templates, test with the media type's *Test* button |
| Teams returns 429 during a big outage | Teams/Power Automate rate limit | Add a retry policy that honours `Retry-After` on the flow's *Post card* action |

## Why not phone calls via a telecom API?
We first tried a third-party voice API (outgoing webhook → TTS call). It needs a
**paid caller ID / DID number** and business KYC. That breaks the zero-cost goal
and adds days of paperwork. The IRM mobile app's *important* push rings like a
phone call, overrides DND and costs nothing, so it replaced voice entirely.

## Why not self-host Grafana OnCall OSS?
OnCall OSS went into maintenance mode on 2025-03-11 and was **archived on
2026-03-24**. Its cloud connection (mobile push, SMS, phone) stopped working for
OSS installs, so a self-hosted stack can no longer ring phones. Grafana Cloud IRM
is the supported path, and its Free tier covers a 3-person rota.

## Safe-change checklist
1. `paging_toggle.py pause` before big changes (it writes a backup).
2. Make the change.
3. `who_is_on_call.py` and `send_test_alert.sh` to verify.
4. `paging_toggle.py resume backups/<file>.json`.
5. Verify the final state yourself. Don't trust a loop's per-item "OK" output.
