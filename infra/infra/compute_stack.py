from pathlib import Path

from aws_cdk import CfnOutput, Stack, aws_ec2 as ec2, aws_ecr as ecr, aws_iam as iam
from constructs import Construct

# infra/infra/compute_stack.py から見たプロジェクトルート（docker-compose.prod.ymlの場所）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CLOUDWATCH_AGENT_CONFIG = """{
  "metrics": {
    "namespace": "StockAnalyzer",
    "metrics_collected": {
      "mem": { "measurement": ["mem_used_percent"], "metrics_collection_interval": 60 },
      "disk": { "measurement": ["disk_used_percent"], "metrics_collection_interval": 60, "resources": ["/"] }
    }
  }
}"""

# default_serverが無いと、DNS切替前(Hostヘッダーがドメイン名と不一致)のIP直接アクセスがnginx標準の
# フォールバックサーバー(nginx.conf組み込みの"server_name _"ブロック、IPv4/IPv6両方でlisten)に
# 落ちて404になる。IPv4のみdefault_server指定してもIPv6経由のアクセスは素通りするため、両方に付与する。
NGINX_CONF = """server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name app.kimura-stock.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
"""

# check_alerts.py はイメージ内に含まれているため、docker compose exec で実行できる。
# cron.d はユーザー個別のcrontabと違いファイル配置だけで有効になるためIaCと相性が良い。
CRONTAB_D = """PATH=/usr/bin:/bin
5 0 * * 1-5 root /usr/bin/docker compose -f /opt/stock-analyzer/docker-compose.yml -p stock-analyzer exec -T app python scripts/check_alerts.py >> /var/log/stock-analyzer/alert.log 2>&1
30 3 * * 1-5 root /usr/bin/docker compose -f /opt/stock-analyzer/docker-compose.yml -p stock-analyzer exec -T app python scripts/check_alerts.py >> /var/log/stock-analyzer/alert.log 2>&1
35 6 * * 1-5 root /usr/bin/docker compose -f /opt/stock-analyzer/docker-compose.yml -p stock-analyzer exec -T app python scripts/check_alerts.py >> /var/log/stock-analyzer/alert.log 2>&1
"""

# certbot自体はpipでインストールしておくが、初回の証明書発行(certbot --nginx -d ...)は
# DNS切替(Phase 9)後にドメインが新EIPを指してから手動実行する(HTTP-01検証の都合上、先に自動化できない)。
# 更新cronだけは先に仕込んでおく(初回発行後は自動更新される)。
CERTBOT_RENEW_CRON = """PATH=/usr/bin:/bin
0 3,15 * * * root /opt/certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
"""


class ComputeStack(Stack):
    """stock-analyzer: ECRリポジトリ・EC2(Docker運用)・EIP"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
        instance_role: iam.IRole,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.repository = ecr.Repository(
            self,
            "AppRepository",
            repository_name="stock-analyzer",
            image_scan_on_push=True,
        )

        compose_template = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        image_ref = f"{self.repository.repository_uri}:latest"
        compose_content = compose_template.replace("__ECR_IMAGE__", image_ref)

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "dnf update -y",
            # cronie: Amazon Linux 2023にはcron(crond)がデフォルトで入っていないため明示インストールが必要
            "dnf install -y docker nginx amazon-cloudwatch-agent cronie",
            "systemctl enable --now docker",
            "systemctl enable --now crond",
            # Amazon Linux 2023のdnfリポジトリにcompose pluginが無いためGitHub releaseから直接取得
            "mkdir -p /usr/libexec/docker/cli-plugins",
            "curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64"
            " -o /usr/libexec/docker/cli-plugins/docker-compose",
            "chmod +x /usr/libexec/docker/cli-plugins/docker-compose",
            "usermod -aG docker ec2-user",
            "mkdir -p /opt/stock-analyzer /var/log/stock-analyzer",
        )
        user_data.add_commands(
            f"cat > /opt/stock-analyzer/docker-compose.yml << 'COMPOSE_EOF'\n{compose_content}COMPOSE_EOF"
        )
        user_data.add_commands(
            "# .env は本番シークレットを含むため、UserDataには書き込まない。"
            " 起動後にSession Manager経由で `sudo tee /opt/stock-analyzer/.env` を手動実行すること",
            f"aws ecr get-login-password --region {self.region}"
            f" | docker login --username AWS --password-stdin {self.account}.dkr.ecr.{self.region}.amazonaws.com",
        )
        user_data.add_commands(
            f"cat > /etc/nginx/conf.d/stock-analyzer.conf << 'NGINX_EOF'\n{NGINX_CONF}NGINX_EOF",
            "rm -f /etc/nginx/conf.d/default.conf",
            "systemctl enable --now nginx",
            "# HTTPS化(certbot)はDNS切替(Phase 9)後、ドメインが新EIPを指してから実行する",
        )
        user_data.add_commands(
            f"cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CW_EOF'\n{CLOUDWATCH_AGENT_CONFIG}\nCW_EOF",
            "/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl"
            " -a fetch-config -m ec2 -s"
            " -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json",
        )
        user_data.add_commands(
            f"cat > /etc/cron.d/stock-analyzer << 'CRON_EOF'\n{CRONTAB_D}CRON_EOF",
            "chmod 644 /etc/cron.d/stock-analyzer",
        )
        user_data.add_commands(
            "dnf install -y python3-pip augeas-libs",
            "python3 -m venv /opt/certbot",
            "/opt/certbot/bin/pip install --upgrade pip",
            "/opt/certbot/bin/pip install certbot certbot-nginx",
            "ln -sf /opt/certbot/bin/certbot /usr/bin/certbot",
            f"cat > /etc/cron.d/certbot-renew << 'CRON_EOF'\n{CERTBOT_RENEW_CRON}CRON_EOF",
            "chmod 644 /etc/cron.d/certbot-renew",
        )
        user_data.add_commands(
            "# .envが用意され次第、以下を手動実行してアプリを起動する:",
            "# cd /opt/stock-analyzer && docker compose -p stock-analyzer pull && docker compose -p stock-analyzer up -d",
            "# DNS切替後、以下を手動実行してHTTPS証明書を発行する:",
            "# certbot --nginx -d app.kimura-stock.com --non-interactive --agree-tos -m <email> --redirect",
        )

        self.instance = ec2.Instance(
            self,
            "AppInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            # "latest"参照はCloudFormationのAWS::SSM::Parameter::Value型パラメータとなり、
            # デプロイの度にその時点の最新AMIへ差し替わり意図しないインスタンス置き換えを招くため、
            # 現在稼働中のAMIに固定する。OSセキュリティパッチ追従は手動でこの値を更新して行う(2026-08-05)
            machine_image=ec2.MachineImage.generic_linux({"ap-northeast-1": "ami-0af8344e5a6a14ac7"}),
            security_group=security_group,
            role=instance_role,
            user_data=user_data,
            # デフォルト8GBはDockerイメージ+問題データDB容量を見込むと手狭なため18GBに拡張(2026-08-05)
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(18, volume_type=ec2.EbsDeviceVolumeType.GP3),
                ),
            ],
        )

        self.eip = ec2.CfnEIP(self, "AppEip", domain="vpc")
        ec2.CfnEIPAssociation(
            self,
            "AppEipAssociation",
            allocation_id=self.eip.attr_allocation_id,
            instance_id=self.instance.instance_id,
        )

        CfnOutput(self, "InstanceId", value=self.instance.instance_id)
        CfnOutput(self, "ElasticIp", value=self.eip.ref)
        CfnOutput(self, "EcrRepositoryUri", value=self.repository.repository_uri)
