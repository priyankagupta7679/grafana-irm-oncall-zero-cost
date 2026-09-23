# Zabbix → Grafana IRM (webhook media type)

1. Create an IRM integration of type **Webhook** (`bootstrap_oncall.py` does this) and copy its URL.
2. In Zabbix: **Alerts → Media types → Create media type**
   - Type: `Webhook`
   - Parameters:

     | Name | Value |
     |---|---|
     | `url` | the IRM webhook URL |
     | `title` | `{EVENT.NAME}` |
     | `message` | `{EVENT.OPDATA}` |
     | `status` | `{EVENT.VALUE}` (1 = problem, 0 = recovery) |
     | `event_id` | `{EVENT.ID}` |
     | `host` | `{HOST.NAME}` |
     | `project` | `app-a` (a label your `routing_regex` matches) |

   - Script:

```javascript
var p = JSON.parse(value);
var req = new HttpRequest();
req.addHeader('Content-Type: application/json');
var body = {
  alert_uid: p.event_id,
  title: '[' + p.project + '] ' + p.title,
  message: p.host + ': ' + p.message,
  state: p.status === '1' ? 'alerting' : 'ok'
};
var resp = req.post(p.url, JSON.stringify(body));
if (req.getStatus() >= 300) {
  throw 'IRM returned ' + req.getStatus() + ': ' + resp;
}
return 'OK';
```

3. **Message templates tab**: add templates for *Problem* and *Problem recovery*.
   Without them, Zabbix silently skips the media type and nothing is sent.
4. Create a user (for example `irm-dispatcher`) with this media type and a
   placeholder "send to" value.
5. Create an **Action** (Alerts → Actions → Trigger actions):
   - Condition: `Trigger severity >= Disaster` (or High)
   - Operation: send to `irm-dispatcher` via the new media type
   - Recovery operation: same, so incidents auto-resolve in IRM
6. Test it from the media type's **Test** button, then check the alert group in IRM.

In the IRM webhook integration, map `alert_uid` to the grouping ID and `state == "ok"`
to auto-resolve (Integration → Templates → *Grouping* / *Autoresolution*):

```jinja
Grouping id:     {{ payload.alert_uid }}
Resolve condition: {{ payload.state == "ok" }}
```
