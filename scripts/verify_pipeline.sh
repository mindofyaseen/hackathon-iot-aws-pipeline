#!/bin/bash
# Run from Kafka Connect EC2 via SSM session
# Usage: bash verify_pipeline.sh <pg_host> <msk_brokers>

PG_HOST=${1:-"REPLACE_WITH_PG_IP"}
MSK_BROKERS=${2:-"REPLACE_WITH_MSK_BROKERS"}
KAFKA_BIN="/opt/confluent/bin"

echo "=== Phase 1 Smoke Test ==="

echo ""
echo "[1] MSK topic list..."
$KAFKA_BIN/kafka-topics.sh --bootstrap-server "$MSK_BROKERS" --list

echo ""
echo "[2] iot-events topic message count (10 second sample)..."
timeout 10 $KAFKA_BIN/kafka-console-consumer.sh \
  --bootstrap-server "$MSK_BROKERS" \
  --topic iot-events \
  --from-beginning \
  --max-messages 5 2>/dev/null || echo "No messages yet or topic not found"

echo ""
echo "[3] Kafka Connect connectors status..."
curl -s http://localhost:8083/connectors | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))"

echo ""
echo "[4] PostgreSQL row count..."
PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -U iot_user -d iotdb \
  -c "SELECT COUNT(*) AS total_rows FROM iot_events;" 2>/dev/null || \
  echo "Cannot reach PostgreSQL (check PG_PASSWORD env var)"

echo ""
echo "[5] PostgreSQL WAL level..."
PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -U iot_user -d iotdb \
  -c "SHOW wal_level;" 2>/dev/null

echo ""
echo "=== Done ==="
