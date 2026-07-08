from aws_cdk import CfnOutput, Stack, aws_route53 as route53
from constructs import Construct


class DnsStack(Stack):
    """stock-analyzer: 既存Route53ホストゾーンの参照のみ(Aレコードの実体はCDK管理外)"""

    DOMAIN_NAME = "kimura-stock.com"

    def __init__(self, scope: Construct, construct_id: str, eip_address: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 新規作成しない。既存の本番ホストゾーンをそのまま参照する
        zone = route53.HostedZone.from_lookup(self, "Zone", domain_name=self.DOMAIN_NAME)

        # 注意: AWS::Route53::RecordSet はCloudFormationのImport機能が非対応のリソースタイプのため、
        # 既存レコード(CloudFormation管理外で作成済み)をCDK管理下に取り込むことができない。
        # そのためAレコード自体はCDKでは作成せず、実際の値の切替は
        # `aws route53 change-resource-record-sets`(UPSERT)で直接行う運用とする。
        # ここではホストゾーンの参照と、意図する値のドキュメント化(Output)のみ行う。
        CfnOutput(self, "HostedZoneId", value=zone.hosted_zone_id)
        CfnOutput(self, "IntendedARecordTarget", value=f"app.{self.DOMAIN_NAME} -> {eip_address}")

        # SESのドメイン検証・DKIM・MAIL FROMは再作成・再検証しない(既にVerified状態を維持)。
        # ここでは実リソースに一切触れず、参照のみに留める。
