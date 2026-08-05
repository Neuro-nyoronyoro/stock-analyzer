from aws_cdk import Stack, aws_ec2 as ec2, aws_iam as iam
from constructs import Construct


class NetworkStack(Stack):
    """stock-analyzer: 既存デフォルトVPC参照・SecurityGroup・EC2用IAMロール"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_name: str,
        ssm_default_kms_key_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 新規VPCは作らず、既存のデフォルトVPCを参照する
        self.vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # SSHは開けない（EC2への接続はSession Manager経由の方針を維持）
        self.security_group = ec2.SecurityGroup(
            self,
            "AppSecurityGroup",
            vpc=self.vpc,
            description="stock-analyzer: allow HTTP/HTTPS inbound only",
            allow_all_outbound=True,
        )
        self.security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP")
        self.security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS")

        self.instance_role = iam.Role(
            self,
            "AppInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                # Session Manager経由の接続に必要
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                # 既存EC2で導入済みのCloudWatchエージェント相当の権限
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
                # ECRからDockerイメージをpullするための読み取り権限
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
            ],
        )

        # check_alerts.py からのSESメール送信用
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=[f"arn:aws:ses:{self.region}:{self.account}:identity/{domain_name}"],
            )
        )

        # MonitoringStack(Phase 8)で作成予定の既存同名SNSトピックに合わせている
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[f"arn:aws:sns:{self.region}:{self.account}:stock-analyzer-alerts"],
            )
        )

        # .env(SecureString)をSSM Parameter Storeから取得するための権限(Phase 9のデプロイ時に追加)
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/stock-analyzer/*"],
            )
        )
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["kms:Decrypt"],
                resources=[ssm_default_kms_key_arn],
            )
        )
