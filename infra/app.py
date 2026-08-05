#!/usr/bin/env python3
import aws_cdk as cdk

from infra.compute_stack import ComputeStack
from infra.dns_stack import DnsStack
from infra.monitoring_stack import MonitoringStack
from infra.network_stack import NetworkStack

app = cdk.App()

# Vpc.from_lookup等のcontext lookupを使うため、env(account/region)の指定が必須
env = cdk.Environment(account="600627320448", region="ap-northeast-1")
domain_name = "kimura-stock.com"
# SSM Parameter Store(SecureString)のデフォルト暗号化に使われるAWS管理キー。
# `aws kms describe-key --key-id alias/aws/ssm`で取得した実キーARN(エイリアスはResourceに指定しても効かないため)
ssm_default_kms_key_arn = "arn:aws:kms:ap-northeast-1:600627320448:key/f8cc4b00-d898-4d46-85a7-605e54770e59"

network = NetworkStack(
    app,
    "StockAnalyzerNetworkStack",
    env=env,
    domain_name=domain_name,
    ssm_default_kms_key_arn=ssm_default_kms_key_arn,
)

compute = ComputeStack(
    app,
    "StockAnalyzerComputeStack",
    env=env,
    vpc=network.vpc,
    security_group=network.security_group,
    instance_role=network.instance_role,
)

DnsStack(
    app,
    "StockAnalyzerDnsStack",
    env=env,
    domain_name=domain_name,
    eip_address=compute.eip.ref,
)

MonitoringStack(
    app,
    "StockAnalyzerMonitoringStack",
    env=env,
    instance=compute.instance,
)

app.synth()
