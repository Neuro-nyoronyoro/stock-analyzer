#!/usr/bin/env python3
import aws_cdk as cdk

from infra.compute_stack import ComputeStack
from infra.dns_stack import DnsStack
from infra.monitoring_stack import MonitoringStack
from infra.network_stack import NetworkStack

app = cdk.App()

# Vpc.from_lookup等のcontext lookupを使うため、env(account/region)の指定が必須
env = cdk.Environment(account="600627320448", region="ap-northeast-1")

network = NetworkStack(app, "StockAnalyzerNetworkStack", env=env)

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
    eip_address=compute.eip.ref,
)

MonitoringStack(
    app,
    "StockAnalyzerMonitoringStack",
    env=env,
    instance=compute.instance,
)

app.synth()
