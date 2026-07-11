#!/bin/bash
# Run on your LOCAL machine after cdk deploy --all completes.
# Requires: AWS CLI configured for account 989864147584, us-east-1
# Usage: bash scripts/post_deploy.sh

set -e
REGION="us-east-1"

# Load .env if it already exists from a previous run
[ -f .env ] && source .env

SNOWFLAKE_PASSWORD="${SNOWFLAKE_PASSWORD:?Set SNOWFLAKE_PASSWORD env var before running: export SNOWFLAKE_PASSWORD=xxx}"

echo "=== Fetching CDK stack outputs ==="

BASTION_ID=$(aws cloudformation describe-stacks \
  --stack-name Ec2Stack --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='BastionInstanceId'].OutputValue" \
  --output text)

PG_IP=$(aws cloudformation describe-stacks \
  --stack-name Ec2Stack --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='PostgresPrivateIp'].OutputValue" \
  --output text)

CONNECT_IP=$(aws cloudformation describe-stacks \
  --stack-name Ec2Stack --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='ConnectPrivateIp'].OutputValue" \
  --output text)

CONNECT_ID=$(aws ec2 describe-instances --region $REGION \
  --filters "Name=private-ip-address,Values=$CONNECT_IP" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text)

MSK_BROKERS=$(aws cloudformation describe-stacks \
  --stack-name MskStack --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='MskBootstrapBrokers'].OutputValue" \
  --output text)

PG_SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name Ec2Stack --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='PgSecretArn'].OutputValue" \
  --output text)

PG_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$PG_SECRET_ARN" --region $REGION \
  --query SecretString --output text | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")

echo "Bastion ID    : $BASTION_ID"
echo "PG Private IP : $PG_IP"
echo "Connect IP    : $CONNECT_IP"
echo "Connect ID    : $CONNECT_ID"
echo "MSK Brokers   : $MSK_BROKERS"

# Save to .env
cat > .env <<EOF
BASTION_ID=$BASTION_ID
PG_HOST=$PG_IP
CONNECT_IP=$CONNECT_IP
CONNECT_ID=$CONNECT_ID
MSK_BROKERS=$MSK_BROKERS
PG_SECRET_ARN=$PG_SECRET_ARN
PG_PASSWORD=$PG_PASSWORD
SNOWFLAKE_ACCOUNT=PLHVTTI-MWC64694
SNOWFLAKE_USER=YASEEN
SNOWFLAKE_PASSWORD=$SNOWFLAKE_PASSWORD
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_WH=COMPUTE_WH
SNOWFLAKE_DB=HACKATHON_IOT
EOF
echo "Saved to .env"

echo ""
echo "=== Installing Kafka Connect plugins on Connect EC2 ==="

SSM_PARAMS=$(cat <<EOF
{
  "commands": [
    "sed -i 's|bootstrap.servers=.*|bootstrap.servers=${MSK_BROKERS}|' /opt/confluent/etc/kafka/connect-distributed.properties",
    "mkdir -p /opt/confluent/plugins/jdbc /opt/confluent/plugins/debezium /opt/confluent/plugins/snowflake",
    "wget -q https://packages.confluent.io/maven/io/confluent/kafka-connect-jdbc/10.7.6/kafka-connect-jdbc-10.7.6.jar -O /opt/confluent/plugins/jdbc/kafka-connect-jdbc.jar",
    "wget -q https://jdbc.postgresql.org/download/postgresql-42.7.3.jar -O /opt/confluent/plugins/jdbc/postgresql-42.7.3.jar",
    "wget -q https://repo1.maven.org/maven2/io/debezium/debezium-connector-postgres/2.5.4.Final/debezium-connector-postgres-2.5.4.Final-plugin.tar.gz -O /tmp/debezium.tar.gz",
    "tar -xzf /tmp/debezium.tar.gz -C /opt/confluent/plugins/debezium --strip-components=1",
    "wget -q https://repo1.maven.org/maven2/com/snowflake/snowflake-kafka-connector/2.1.0/snowflake-kafka-connector-2.1.0.jar -O /opt/confluent/plugins/snowflake/snowflake-kafka-connector.jar",
    "wget -q https://repo1.maven.org/maven2/net/snowflake/snowflake-jdbc/3.14.4/snowflake-jdbc-3.14.4.jar -O /opt/confluent/plugins/snowflake/snowflake-jdbc.jar",
    "systemctl restart kafka-connect",
    "sleep 15 && curl -s http://localhost:8083/connector-plugins | python3 -c 'import sys,json; [print(p[\"class\"]) for p in json.load(sys.stdin)]'",
    "echo PLUGINS_DONE"
  ]
}
EOF
)

aws ssm send-command \
  --instance-ids "$CONNECT_ID" \
  --document-name "AWS-RunShellScript" \
  --region $REGION \
  --parameters "$SSM_PARAMS" \
  --output text --query "Command.CommandId"

echo "Waiting 90s for plugins to install and Connect to restart..."
sleep 90

echo ""
echo "=== Deploying JDBC Sink Connector ==="

JDBC_JSON=$(cat kafka-connect/jdbc-sink-connector.json \
  | sed "s|\${PG_HOST}|$PG_IP|g" \
  | sed "s|\${PG_PASSWORD}|$PG_PASSWORD|g" \
  | tr -d '\n')

aws ssm send-command \
  --instance-ids "$BASTION_ID" \
  --document-name "AWS-RunShellScript" \
  --region $REGION \
  --parameters "commands=[
    \"curl -s -X POST http://$CONNECT_IP:8083/connectors -H 'Content-Type: application/json' -d '$JDBC_JSON'\",
    \"echo JDBC_DEPLOYED\"
  ]" \
  --output text --query "Command.CommandId"

echo "JDBC sink connector deployed."

echo ""
echo "=== Deploying Debezium Source Connector ==="

DEBEZIUM_JSON=$(cat kafka-connect/debezium-source.json \
  | sed "s|\${PG_HOST}|$PG_IP|g" \
  | sed "s|\${PG_PASSWORD}|$PG_PASSWORD|g" \
  | tr -d '\n')

aws ssm send-command \
  --instance-ids "$BASTION_ID" \
  --document-name "AWS-RunShellScript" \
  --region $REGION \
  --parameters "commands=[
    \"curl -s -X POST http://$CONNECT_IP:8083/connectors -H 'Content-Type: application/json' -d '$DEBEZIUM_JSON'\",
    \"echo DEBEZIUM_DEPLOYED\"
  ]" \
  --output text --query "Command.CommandId"

echo "Debezium source connector deployed."

echo ""
echo "=== Deploying Snowflake Sink Connector ==="

SNOWFLAKE_JSON=$(cat kafka-connect/snowflake-sink.json \
  | sed "s|\${SNOWFLAKE_PASSWORD}|$SNOWFLAKE_PASSWORD|g" \
  | tr -d '\n')

aws ssm send-command \
  --instance-ids "$BASTION_ID" \
  --document-name "AWS-RunShellScript" \
  --region $REGION \
  --parameters "commands=[
    \"curl -s -X POST http://$CONNECT_IP:8083/connectors -H 'Content-Type: application/json' -d '$SNOWFLAKE_JSON'\",
    \"echo SNOWFLAKE_DEPLOYED\"
  ]" \
  --output text --query "Command.CommandId"

echo "Snowflake sink connector deployed."

echo ""
echo "=== All connectors deployed ==="
echo "Next: python scripts/iot_simulator.py --iterations 100"
echo "Then: bash scripts/verify_pipeline.sh \$PG_IP '\$MSK_BROKERS'"
