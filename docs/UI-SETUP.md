# UI Setup Guide: Grafana IRM (click by click)

Part A is required UI work that no script can do: accounts, invites, tokens and
phones. Part B is optional. It is the manual version of what
`bootstrap_oncall.py` automates, for anyone who wants to do everything in the UI
or understand what the script built.

> Menu names are from the Grafana Cloud UI at the time of writing and may move
> slightly between releases.

---

## Part A: required UI steps

### A1. Create a free Grafana Cloud stack
1. Sign up at **grafana.com**, choose the **Free** plan (no credit card needed).
2. Create a stack, e.g. `yourteam.grafana.net`. Pick the region closest to you.
3. Open the stack → left menu → **Alerts & IRM → IRM**. The IRM app is
   pre-installed on Cloud stacks.

### A2. Invite your on-call engineers (max 3 on Free)
1. **grafana.com → My Account → your org → Members → Invite member**, or
   **Administration → Users and access → Users → Invite** inside the stack.
2. Give each engineer at least the **Editor** role. Viewers can't acknowledge.
3. **SSO gotcha:** if your company uses Microsoft/Google SSO, logging in with
   SSO does *not* create a user. They see *"contact your org admin for an
   invite"*. An admin must send the invite first, then SSO works.
4. Remember: anyone in a schedule/escalation chain, or anyone who acknowledges
   or resolves an alert, becomes an **active IRM user**. Keep it to 3 on Free.

### A3. Create the IRM API token (for the scripts)
1. **IRM → Settings → Admin & API** (in older UIs: *OnCall → Settings → API*).
2. Copy the **OnCall API URL** into `ONCALL_API_URL` in `.env`.
3. **Create API token** → name it `bootstrap` → copy into `ONCALL_API_TOKEN`.
   It is shown once. Store it in a password manager and never commit it.

### A4. Each engineer: install and connect the mobile app
1. Install **Grafana IRM** from Play Store / App Store.
2. In the browser: **IRM → Users → (your profile) → Mobile app connection**
   (or the *IRM* tab on your user profile) → a QR code appears.
3. In the app, scan the QR code. The app shows the stack name when connected.

### A5. Each engineer: allow the alert to wake you up
This step decides whether a 3 a.m. alert actually wakes someone.
- **Android:** App → Settings → *Important notifications* → enable
  **Override Do Not Disturb**, pick a loud sound, allow full-screen alerts.
  Exclude the app from battery optimisation.
- **iOS:** allow **Critical Alerts** when prompted (or Settings → Notifications
  → Grafana IRM → Critical Alerts ON).
- Test it: in the app, *Settings → Send test notification* while the phone is
  locked and on silent.

### A6. Each engineer: set personal notification rules
**IRM → Users → your profile → Notification rules.**

| Rule set | Suggested steps |
|---|---|
| **Default notifications** | Mobile push → wait 5 min → Mobile push |
| **Important notifications** (used by this setup) | Mobile push *important* → wait 2 min → Mobile push *important* |

The escalation chain created by the script marks every page as **important**,
so the *Important* rules are what fire at night.

Optional: Grafana IRM also includes built-in **phone call / SMS** at no extra
cost. You must verify your number in the profile (E.164 format, e.g.
`+<country><number>`). Delivery depends on the carrier and country, so test
before relying on it. This project uses mobile push as the primary channel.

### A7. Create the Teams webhook URL
Either:
- **Teams → channel → ••• → Workflows → "Post to a channel when a webhook
  request is received"** → copy the URL (recommended; old Office 365
  connectors are being retired), or
- a classic **Incoming Webhook** connector, if your tenant still allows it.

Paste it into `TEAMS_WEBHOOK_URL` in `.env`. The URL is a secret: anyone with it
can post to your channel.

### A8. Run the scripts
```bash
python scripts/bootstrap_oncall.py --dry-run   # read the plan
python scripts/bootstrap_oncall.py             # build it
```
Copy the printed integration URLs into your alert sources (see `examples/`).

---

## Part B: doing it all in the UI (manual equivalent)

### B1. Schedules: after-hours only
**IRM → Schedules → + New schedule → Set up on-call rotation schedule (web).**
1. Name: `tier1-after-hours`, timezone = your team's timezone.
2. **+ Add rotation** → *Weekly*.
   - Users: engineer 1
   - Start: Monday at your business-hours **end** time (e.g. 18:30)
   - **Mask by weekdays:** Mon, Tue, Wed, Thu
   - Shift duration: until the next business start (e.g. 15h30m → 10:00)
3. **+ Add rotation** → *Weekly*.
   - Start: Friday at your business-hours end (18:30)
   - Mask by weekdays: Fri
   - Duration: until Monday business start (e.g. 63h30m → Mon 10:00)
4. Repeat for `tier2-after-hours`, `tier3-after-hours`.
5. Optional `all-tiers-after-hours`: same two rotations, with all 3 users added
   as **one group**, so they are on shift together.
6. Check the preview. It should be **empty** during business hours.

> Public holidays: add an **Override** on the schedule for that day.
> Swaps: engineers can request **shift swaps** from the app.

### B2. Escalation chain
**IRM → Escalation chains → + New escalation chain** → `app-a-after-hours`.

| # | Step | Setting |
|---|---|---|
| 0 | Wait | 6 min (grace period for flapping alerts) |
| 1 | Notify users from on-call schedule | `tier1-after-hours`, **Important** ✔ |
| 2 | Wait | 10 min |
| 3 | Notify users from on-call schedule | `tier2-after-hours`, **Important** ✔ |
| 4 | Wait | 10 min |
| 5 | Notify users from on-call schedule | `tier3-after-hours`, **Important** ✔ |
| 6 | Wait | 10 min |
| 7 | Notify users from on-call schedule | `all-tiers-after-hours`, **Important** ✔ |

Do **not** use *Notify users* (direct) steps. They ignore schedules and page
people during business hours too.

### B3. Integrations
**IRM → Integrations → + New integration**:
- *Alertmanager* for Prometheus
- *Amazon SNS* for CloudWatch
- *Webhook* for Zabbix or anything custom
- *Grafana Alerting* for Grafana-managed alert rules

Copy each integration's URL. Treat it like a password.

### B4. Routes (one per environment)
Open the integration → **+ Add route**:
- Routing template / regex: `(?i)app-a` → escalation chain `app-a-after-hours`
- Another route: `(?i)app-b` → `app-b-after-hours`
- **Default route** → your primary chain (catches anything unmatched)

Non-default routes are evaluated top to bottom before the default.

### B5. Teams outgoing webhooks (24x7 visibility)
**IRM → Outgoing webhooks → + Create** (twice):

| Field | FIRING webhook | RESOLVED webhook |
|---|---|---|
| Trigger type | *Alert Group Created* | *Resolved* |
| HTTP method | POST | POST |
| URL | Teams webhook URL | Teams webhook URL |
| Forward whole payload | **OFF** | **OFF** |
| Data | `templates/teams-firing.json.j2` | `templates/teams-resolved.json.j2` |
| Trigger template (multi-channel only) | `{{ 'app-a' in alert_group.title }}` | same |

### B6. Verify end-to-end
1. `python scripts/who_is_on_call.py`: during business hours every schedule
   should say *nobody*.
2. `./scripts/send_test_alert.sh <alertmanager-integration-url> firing app-a`
   - Business hours: Teams card appears, **no** push. ✅
   - After hours: Teams card, then the tier-1 phone rings at T+6 min. ✅
3. On the phone, tap **Silence** to test escalation to tier 2, then
   **Acknowledge** to confirm escalation stops.
4. `./scripts/send_test_alert.sh <url> resolved app-a` → Teams RESOLVED card. ✅
