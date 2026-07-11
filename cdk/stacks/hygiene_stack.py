import os
from aws_cdk import (
    Stack,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    Duration,
)
from constructs import Construct


class HygieneStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        alert_email = os.environ.get("BILLING_ALERT_EMAIL", "mindofyaseen@gmail.com")

        topic = sns.Topic(self, "BillingAlertTopic", display_name="Hackathon Billing Alert")
        topic.add_subscription(subs.EmailSubscription(alert_email))

        billing_alarm = cw.Alarm(
            self,
            "BillingAlarm50USD",
            alarm_name="hackathon-billing-50usd",
            alarm_description="Estimated AWS charges exceeded $50",
            metric=cw.Metric(
                namespace="AWS/Billing",
                metric_name="EstimatedCharges",
                dimensions_map={"Currency": "USD"},
                period=Duration.hours(6),
                statistic="Maximum",
            ),
            threshold=50,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        billing_alarm.add_alarm_action(cw_actions.SnsAction(topic))
