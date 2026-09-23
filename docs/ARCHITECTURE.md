# Flow Architecture

All diagrams are Mermaid, so GitHub renders them directly.

## 1. End-to-end flow

```mermaid
flowchart LR
    subgraph Sources["Alert sources (any mix)"]
        PM[Prometheus] --> AM[Alertmanager<br/>critical only]
        CW[CloudWatch Alarm] --> SNS[Amazon SNS topic]
        ZB[Zabbix trigger<br/>Disaster / High]
        GA[Grafana Alerting]
    end

    subgraph IRM["Grafana IRM (Grafana Cloud Free)"]
        INT[Integrations<br/>Alertmanager · SNS · Webhook]
        RT{Routes<br/>regex on alert title/labels}
        AG[(Alert group<br/>dedup + grouping)]
        EC[Escalation chain<br/>per environment]
        SCH[After-hours schedules<br/>tier1 · tier2 · tier3 · all]
        OW[Outgoing webhooks<br/>FIRING / RESOLVED]
    end

    AM -->|webhook| INT
    SNS -->|HTTPS subscription| INT
    ZB -->|webhook media type| INT
    GA -->|contact point| INT

    INT --> AG --> RT --> EC
    EC -->|who is on shift now?| SCH
    SCH -->|after hours| APP[📱 Grafana IRM mobile app<br/>push notification, overrides DND]
    SCH -.->|business hours: nobody on shift| SKIP[step skipped silently]
    AG --> OW --> TEAMS[💬 Microsoft Teams channel<br/>24x7]

    APP -->|Acknowledge| AG
    APP -->|Resolve| AG
```

**Key idea:** Teams notifications hang off the alert group itself, while phone
paging hangs off the escalation chain. They are independent, so every alert is
posted to Teams, and only the paging depends on the time of day.

## 2. Business-hours decision (no code, no cron)

```mermaid
flowchart TD
    A[Alert group created] --> T[Teams FIRING card posted]
    A --> W[Escalation step 0: wait N min]
    W --> R{Auto-resolved<br/>during wait?}
    R -->|yes| Q[Teams RESOLVED card<br/>nobody paged]
    R -->|no| S{Is anyone on shift<br/>in tier-1 schedule?}
    S -->|"No: business hours<br/>(Mon–Fri 10:00–18:30)"| N[Step skipped<br/>→ team handles it from Teams]
    S -->|"Yes: nights, weekends"| P[📱 Page tier-1<br/>important notification]
```

The schedules contain **only** after-hours shifts. Inside business hours they are
empty, so `notify_on_call_from_schedule` finds nobody and moves on. No
time-based scripts, cron jobs or paid features are involved.

## 3. Weekly coverage

Two shifts per schedule cover every minute outside business hours:

```mermaid
gantt
    title After-hours shifts (example: business hours Mon–Fri 10:00–18:30)
    dateFormat  YYYY-MM-DD HH:mm
    axisFormat  %a %H:%M
    section Weeknight shift (MO,TU,WE,TH)
    Mon night  :a1, 2026-01-05 18:30, 15h30m
    Tue night  :a2, 2026-01-06 18:30, 15h30m
    Wed night  :a3, 2026-01-07 18:30, 15h30m
    Thu night  :a4, 2026-01-08 18:30, 15h30m
    section Weekend shift (FR)
    Fri 18:30 → Mon 10:00 :b1, 2026-01-09 18:30, 63h30m
```

`bootstrap_oncall.py` works these windows out from `business_hours` in
`config.yaml`, so you only change the times there.

## 4. Escalation timeline (after hours)

```mermaid
sequenceDiagram
    autonumber
    participant S as Alert source
    participant I as Grafana IRM
    participant T as Teams
    participant E1 as Tier 1 phone
    participant E2 as Tier 2 phone
    participant E3 as Tier 3 phone

    S->>I: alert (FIRING)
    I->>T: FIRING card (T+0)
    Note over I: wait 6 min (flaps auto-resolve here)
    I->>E1: push (T+6)
    Note over I: wait 10 min
    I->>E2: push (T+16) if not acknowledged
    Note over I: wait 10 min
    I->>E3: push (T+26)
    Note over I: wait 10 min
    I->>E1: push everyone (T+36)
    E2-->>I: Acknowledge (escalation stops)
    S->>I: alert (RESOLVED)
    I->>T: RESOLVED card
```

**Acknowledge** stops escalation. **Silence** only mutes it for a while, so tell the
team which one to use.

## 5. Multi-environment routing

```mermaid
flowchart LR
    INT[Integration] --> R1{"regex (?i)app-a"} -->|match| C1[app-a-after-hours chain]
    INT --> R2{"regex (?i)app-b"} -->|match| C2[app-b-after-hours chain]
    INT --> RD[default route] --> C1
    OW1[Teams-Firing webhook] -.->|"trigger_template:<br/>'app-a' in alert_group.title"| TA[Teams: app-a channel]
    OW2[Teams-Firing webhook] -.->|"'app-b' in alert_group.title"| TB[Teams: app-b channel]
```

- Non-default routes are evaluated first, in order. The default route catches the rest.
- With more than one Teams channel, give each outgoing webhook a **trigger
  template**. Without it, every webhook fires for every alert and projects cross-post.

## 6. Pause switch

```mermaid
flowchart LR
    P[paging_toggle.py pause] --> B[(backups/routes_*.json)]
    P --> D[routes → escalation_chain = none]
    D --> X[Alerts + Teams keep working<br/>phones silent]
    B --> R[paging_toggle.py resume file] --> Y[routes restored exactly]
```

## Cost breakdown

Full limits are in the [README](../README.md#-cost--free-tier-limits-read-this-first).

| Component | Cost |
|---|---|
| Grafana Cloud Free: IRM, schedules, escalation, mobile push | $0 for up to **3 active IRM users** per month |
| Grafana IRM mobile app (Android / iOS) | $0 |
| Microsoft Teams Workflows / incoming webhook | $0 with an existing M365 licence |
| Amazon SNS HTTPS deliveries | $0 within the free tier for normal alert volume |
| Alertmanager / Zabbix | $0 (self-hosted, already running) |
| Voice calls / SMS via a third-party telecom API | **Not used**. These need a paid caller ID / DID number. |
