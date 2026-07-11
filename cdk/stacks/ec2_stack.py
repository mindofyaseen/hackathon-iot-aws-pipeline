import json
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_secretsmanager as sm,
    CfnOutput,
)
from constructs import Construct


POSTGRES_USER_DATA = """#!/bin/bash
set -e
yum update -y

amazon-linux-extras enable postgresql14
yum install -y postgresql-server postgresql postgresql-contrib

postgresql-setup initdb
systemctl enable postgresql
systemctl start postgresql

PG_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id /hackathon/postgres/credentials \
    --region {region} \
    --query SecretString --output text)

PG_PASSWORD=$(echo "$PG_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")

sudo -u postgres psql -c "CREATE USER iot_user WITH PASSWORD '$PG_PASSWORD' REPLICATION LOGIN;"
sudo -u postgres psql -c "CREATE DATABASE iotdb OWNER iot_user;"
sudo -u postgres psql -d iotdb -c "
  CREATE TABLE IF NOT EXISTS iot_events (
    id          BIGSERIAL PRIMARY KEY,
    device_id   VARCHAR(64) NOT NULL,
    lat         NUMERIC(10, 6),
    long        NUMERIC(10, 6),
    temperature NUMERIC(6, 2),
    aqi         NUMERIC(6, 2),
    ts          TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
  );
"

sed -i "s/#wal_level = replica/wal_level = logical/" /var/lib/pgsql/data/postgresql.conf
sed -i "s/max_replication_slots = 10/max_replication_slots = 10/" /var/lib/pgsql/data/postgresql.conf

cat >> /var/lib/pgsql/data/pg_hba.conf <<'EOF'
host    iotdb           iot_user        10.0.0.0/8              md5
host    replication     iot_user        10.0.0.0/8              md5
EOF

systemctl restart postgresql
"""

CONNECT_USER_DATA = """#!/bin/bash
set -e
yum update -y
yum install -y java-11-amazon-corretto wget

CONFLUENT_VERSION=7.6.0
wget -q https://packages.confluent.io/archive/7.6/confluent-community-7.6.0.tar.gz -O /tmp/confluent.tar.gz
mkdir -p /opt/confluent
tar -xzf /tmp/confluent.tar.gz -C /opt/confluent --strip-components=1

mkdir -p /opt/confluent/plugins

MSK_BROKERS=$(aws ssm get-parameter \
  --name "/hackathon/msk/bootstrap-brokers" \
  --region {region} \
  --query "Parameter.Value" \
  --output text 2>/dev/null || echo "localhost:9092")

cat > /opt/confluent/etc/kafka/connect-distributed.properties <<EOF
bootstrap.servers=$MSK_BROKERS
group.id=hackathon-connect-cluster
key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
key.converter.schemas.enable=false
value.converter.schemas.enable=false
offset.storage.topic=connect-offsets
config.storage.topic=connect-configs
status.storage.topic=connect-status
offset.storage.replication.factor=1
config.storage.replication.factor=1
status.storage.replication.factor=1
plugin.path=/opt/confluent/share/java,/opt/confluent/plugins
rest.host.name=0.0.0.0
rest.port=8083
EOF

cat > /etc/systemd/system/kafka-connect.service <<'EOF'
[Unit]
Description=Kafka Connect
After=network.target
[Service]
Type=simple
ExecStart=/opt/confluent/bin/connect-distributed /opt/confluent/etc/kafka/connect-distributed.properties
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable kafka-connect
systemctl start kafka-connect
"""


class Ec2Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, vpc_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = vpc_stack.vpc
        postgres_sg = vpc_stack.postgres_sg
        connect_sg = vpc_stack.connect_sg
        bastion_sg = vpc_stack.bastion_sg

        self.pg_secret = sm.Secret(
            self,
            "PostgresCredentials",
            secret_name="/hackathon/postgres/credentials",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "iot_user"}),
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=24,
            ),
        )

        ssm_policy = iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        secrets_policy = iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[self.pg_secret.secret_arn],
        )

        postgres_role = iam.Role(
            self,
            "PostgresEc2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[ssm_policy],
        )
        postgres_role.add_to_policy(secrets_policy)

        amzn_linux = ec2.MachineImage.latest_amazon_linux2()

        self.postgres_instance = ec2.Instance(
            self,
            "PostgresEc2",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
            machine_image=amzn_linux,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=postgres_sg,
            role=postgres_role,
            user_data=ec2.UserData.custom(
                POSTGRES_USER_DATA.replace("{region}", self.region)
            ),
        )

        connect_role = iam.Role(
            self,
            "ConnectEc2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[ssm_policy],
        )
        connect_role.add_to_policy(secrets_policy)
        connect_role.add_to_policy(
            iam.PolicyStatement(
                actions=["kafka:*", "kafka-cluster:*"],
                resources=["*"],
            )
        )

        self.connect_instance = ec2.Instance(
            self,
            "KafkaConnectEc2",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
            machine_image=amzn_linux,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=connect_sg,
            role=connect_role,
            user_data=ec2.UserData.custom(
                CONNECT_USER_DATA.replace("{region}", self.region)
            ),
        )

        bastion_role = iam.Role(
            self,
            "BastionEc2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[ssm_policy],
        )

        self.bastion_instance = ec2.Instance(
            self,
            "BastionEc2",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
            machine_image=amzn_linux,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=bastion_sg,
            role=bastion_role,
        )

        CfnOutput(self, "PostgresPrivateIp", value=self.postgres_instance.instance_private_ip, export_name="HackathonPostgresIp")
        CfnOutput(self, "ConnectPrivateIp", value=self.connect_instance.instance_private_ip, export_name="HackathonConnectIp")
        CfnOutput(self, "BastionInstanceId", value=self.bastion_instance.instance_id, export_name="HackathonBastionId")
        CfnOutput(self, "PgSecretArn", value=self.pg_secret.secret_arn, export_name="HackathonPgSecretArn")
