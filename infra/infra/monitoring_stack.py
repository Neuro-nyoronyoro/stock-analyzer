from aws_cdk import (
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_sns as sns,
)
from constructs import Construct

START_STOP_LAMBDA_CODE = """
import boto3

def handler(event, context):
    ec2 = boto3.client("ec2")
    action = event["action"]
    instance_id = event["instance_id"]
    if action == "start":
        ec2.start_instances(InstanceIds=[instance_id])
    elif action == "stop":
        ec2.stop_instances(InstanceIds=[instance_id])
"""


class MonitoringStack(Stack):
    """stock-analyzer: SNS通知・CloudWatchアラーム・EC2起動停止スケジュール"""

    def __init__(self, scope: Construct, construct_id: str, instance: ec2.Instance, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 既存の本番SNSトピック(メール購読済み)を参照するのみ。新規作成・再購読はしない
        topic = sns.Topic.from_topic_arn(
            self,
            "AlertsTopic",
            topic_arn=f"arn:aws:sns:{self.region}:{self.account}:stock-analyzer-alerts",
        )

        # 注意: 同名の既存アラーム(旧EC2向け)がCloudFormation管理外に存在する。
        # Phase 9でこのスタックをdeployする前に、旧アラームを手動削除しておくこと(名前衝突を避けるため)。
        common_dimensions = {"InstanceId": instance.instance_id}

        memory_alarm = cloudwatch.Alarm(
            self,
            "MemoryAlarm",
            alarm_name="stock-analyzer-memory",
            metric=cloudwatch.Metric(
                namespace="StockAnalyzer",
                metric_name="mem_used_percent",
                dimensions_map=common_dimensions,
                period=Duration.minutes(1),
                statistic="Average",
            ),
            threshold=80,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )
        memory_alarm.add_alarm_action(cw_actions.SnsAction(topic))

        disk_alarm = cloudwatch.Alarm(
            self,
            "DiskAlarm",
            alarm_name="stock-analyzer-disk",
            metric=cloudwatch.Metric(
                namespace="StockAnalyzer",
                metric_name="disk_used_percent",
                dimensions_map=common_dimensions,
                period=Duration.minutes(1),
                statistic="Average",
            ),
            threshold=80,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )
        disk_alarm.add_alarm_action(cw_actions.SnsAction(topic))

        # EC2起動・停止用Lambda(boto3のstart_instances/stop_instances)
        start_stop_role = iam.Role(
            self,
            "StartStopLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        start_stop_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ec2:StartInstances", "ec2:StopInstances"],
                resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/{instance.instance_id}"],
            )
        )

        start_stop_fn = lambda_.Function(
            self,
            "StartStopFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            role=start_stop_role,
            timeout=Duration.seconds(30),
            code=lambda_.Code.from_inline(START_STOP_LAMBDA_CODE),
        )

        # JST 7:00 起動 = UTC 22:00(前日)
        events.Rule(
            self,
            "StartRule",
            schedule=events.Schedule.cron(minute="0", hour="22"),
            targets=[
                targets.LambdaFunction(
                    start_stop_fn,
                    event=events.RuleTargetInput.from_object(
                        {"action": "start", "instance_id": instance.instance_id}
                    ),
                )
            ],
        )
        # JST 21:00 停止 = UTC 12:00
        events.Rule(
            self,
            "StopRule",
            schedule=events.Schedule.cron(minute="0", hour="12"),
            targets=[
                targets.LambdaFunction(
                    start_stop_fn,
                    event=events.RuleTargetInput.from_object(
                        {"action": "stop", "instance_id": instance.instance_id}
                    ),
                )
            ],
        )
