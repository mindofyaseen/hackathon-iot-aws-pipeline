# IoT On-Premise to AWS Cloud Migration

Hackathon project for instructor Qasim Hassan, Batch 03.

Two-phase pipeline: simulated IoT sensors -> AWS MSK -> PostgreSQL -> Snowflake -> dbt -> Streamlit.

---

## Architecture

**Phase 1:** IoT Sensors -> AWS IoT Core (MQTT) -> MSK (iot-events) -> Kafka Connect JDBC Sink -> PostgreSQL EC2

**Phase 2:** PostgreSQL WAL -> Debezium CDC -> MSK (cdc.public.iot_events) -> Snowflake Kafka Connector -> Snowflake RAW -> dbt silver -> dbt gold -> Streamlit Dashboard

---

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` returns your account)
- Python 3.9+ and Node.js 18+
- AWS CDK: `npm install -g aws-cdk`
- Snowflake account: PLHVTTI-MWC64694 (URL: PLHVTTI-MWC64694.snowflakecomputing.com)

---

## Phase 1 Setup

### 1. Install CDK dependencies

```bash
cd cdk
python -m venv .venv
.venv/Scripts/pip install --no-cache-dir -r requirements.txt
```

### 2. Bootstrap CDK

```bash
cd cdk
cdk bootstrap aws://989864147584/us-east-1
```

### 3. Synthesize (no deploy)

```bash
cdk synth
```

### 4. Deploy (costs ~$5/day -- destroy when done)

```bash
cdk deploy --all --require-approval never
```

### 5. Get outputs

```bash
aws cloudformation describe-stacks --stack-name Ec2Stack --query "Stacks[0].Outputs"
aws cloudformation describe-stacks --stack-name MskStack --query "Stacks[0].Outputs"
```

### 5b. Run post-deploy automation

```bash
# Set Snowflake password in env before running
export SNOWFLAKE_PASSWORD=your_snowflake_password
bash scripts/post_deploy.sh
```

This script: fetches all stack outputs, updates MSK brokers in Kafka Connect config, installs all connector plugins (JDBC, Debezium, Snowflake), then deploys all 3 connectors. It also writes a local `.env` file with runtime values (PG IP, MSK brokers, etc).

### 6. Connect to PostgreSQL via SSM

```bash
# Get bastion instance ID from outputs then:
aws ssm start-session --target <BASTION_INSTANCE_ID> --region us-east-1

# From bastion shell:
psql -h <POSTGRES_PRIVATE_IP> -U iot_user -d iotdb
```

### 7. Initialize PostgreSQL

```bash
psql -h <POSTGRES_PRIVATE_IP> -U postgres -f scripts/postgres_init.sql
```

### 8. Deploy Kafka Connect JDBC Sink

```bash
# From Connect EC2 (via SSM session):
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @kafka-connect/jdbc-sink-connector.json
```

### 9. Run IoT simulator

```bash
pip install boto3
python scripts/iot_simulator.py --iterations 0
```

### 10. Verify Phase 1

```bash
bash scripts/verify_pipeline.sh <PG_IP> <MSK_BROKERS>
```

---

## Phase 2 Setup

### 1. Snowflake setup

Run `scripts/snowflake_setup.sql` in Snowflake UI or SnowSQL.

### 2. Deploy Debezium connector

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @kafka-connect/debezium-source.json
```

### 3. Deploy Snowflake Kafka connector

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @kafka-connect/snowflake-sink.json
```

### 4. Run dbt

```bash
cd dbt
pip install dbt-snowflake

# Load env vars from .env (copy from .env.example and fill password)
export SNOWFLAKE_ACCOUNT=PLHVTTI-MWC64694
export SNOWFLAKE_USER=YASEEN
export SNOWFLAKE_PASSWORD=<your_snowflake_password>
export SNOWFLAKE_ROLE=ACCOUNTADMIN
export SNOWFLAKE_WH=COMPUTE_WH

dbt deps
dbt debug
dbt run
dbt test
dbt docs generate && dbt docs serve
```

### 5. Run Streamlit dashboard

```bash
cd streamlit
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Fill in your Snowflake password in secrets.toml
streamlit run app.py
```

---

## Destroy (stop billing)

```bash
cd cdk
cdk destroy --all
```

---

## Cost Estimate

| Resource | Daily Cost |
|---|---|
| MSK 2x kafka.t3.small | ~$2.19 |
| NAT Gateway | ~$1.08 |
| EC2 (3 instances) | ~$1.50 |
| Total | ~$5/day |
