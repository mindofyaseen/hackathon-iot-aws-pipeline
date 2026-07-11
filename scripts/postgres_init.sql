-- Run this on PostgreSQL EC2 after cdk deploy
-- Connect via: psql -h localhost -U postgres

-- 1. Create user and database
CREATE USER iot_user WITH PASSWORD 'REPLACE_WITH_SECRET' REPLICATION LOGIN;
CREATE DATABASE iotdb OWNER iot_user;

\connect iotdb

-- 2. Create table
CREATE TABLE IF NOT EXISTS iot_events (
    id          BIGSERIAL PRIMARY KEY,
    device_id   VARCHAR(64)  NOT NULL,
    lat         NUMERIC(10,6),
    long        NUMERIC(10,6),
    temperature NUMERIC(6,2),
    aqi         NUMERIC(6,2),
    ts          TIMESTAMPTZ  NOT NULL,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- 3. Index for Debezium CDC queries
CREATE INDEX idx_iot_events_device_ts ON iot_events (device_id, ts);

-- 4. Enable logical replication (requires restart if not already set)
ALTER SYSTEM SET wal_level = logical;
ALTER SYSTEM SET max_replication_slots = 10;
ALTER SYSTEM SET max_wal_senders = 10;

-- 5. Create replication slot for Debezium (run AFTER pg restart)
-- SELECT pg_create_logical_replication_slot('debezium_slot', 'pgoutput');

-- 6. Grant permissions
GRANT ALL PRIVILEGES ON DATABASE iotdb TO iot_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO iot_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO iot_user;

-- 7. Verify
SHOW wal_level;
SELECT COUNT(*) FROM iot_events;
