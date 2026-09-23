# AWS CloudWatch → SNS → Grafana IRM

Cost: SNS HTTPS deliveries are within the AWS free tier for normal alert volumes
(the first 100,000 HTTP/S notifications per month are free, but check your region's pricing).

1. In Grafana IRM create an integration of type **Amazon SNS**, or let
   `bootstrap_oncall.py` do it. Copy its URL.
2. Create (or reuse) an SNS topic and subscribe the URL:

```bash
TOPIC_ARN=$(aws sns create-topic --name oncall-critical --query TopicArn --output text)

aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol https \
  --notification-endpoint "$GRAFANA_IRM_SNS_URL"
```

   IRM confirms the subscription automatically. Check with
   `aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN"`: the status should
   not be `PendingConfirmation`.

3. Point alarms at the topic for **both** ALARM and OK so incidents auto-resolve:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "app-a-db-cpu-high" \
  --namespace AWS/RDS --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=YOUR_DB_INSTANCE \
  --statistic Average --period 300 --evaluation-periods 3 \
  --threshold 90 --comparison-operator GreaterThanThreshold \
  --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN"
```

Put the environment name (for example `app-a`) in the alarm name. IRM routes on it
through the `routing_regex` in `config.yaml`.
