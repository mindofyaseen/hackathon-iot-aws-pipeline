# Architecture -- IoT On-Premise to AWS Cloud Migration

## Phase 1 Flow

```
[IoT Simulator (5 devices)]
         |
         | MQTT  iot/sensors/#
         v
[AWS IoT Core]
         |
         | IoT Topic Rule --> Kafka Action
         | (VPC Destination)
         v
[AWS MSK Kafka]  <-- private subnet, kafka.t3.small x2
   Topic: iot-events
         |
         | Kafka Connect JDBC Sink
         v
[PostgreSQL EC2]  <-- t3.medium, private subnet
   DB: iotdb
   Table: public.iot_events
   wal_level = logical
         |
         | (optional) S3 Sink Connector
         v
[S3 Backup Bucket]  <-- encrypted, 30-day lifecycle

Access path:
[You] --> SSM Session Manager --> [Bastion EC2 t3.micro] --> [PostgreSQL EC2]
                                                         --> [Kafka Connect EC2 t3.small]
```

## Phase 2 Flow

```
[PostgreSQL EC2]
   wal_level=logical
         |
         | Debezium PostgreSQL Source Connector
         | (reads WAL via replication slot)
         v
[AWS MSK Kafka]
   Topic: cdc.public.iot_events
         |
         | Snowflake Kafka Sink Connector
         v
[Snowflake -- HACKATHON_IOT]
   Schema RAW  --> IOT_EVENTS (VARIANT, raw CDC envelope)
         |
         | dbt silver model
         v
   Schema CLEAN --> STG_IOT_EVENTS
   (parsed, typed, aqi_severity tag)
         |
         | dbt gold model
         v
   Schema ANALYTICS --> AGG_DEVICE_DAILY
   (GROUP BY device_id + date, 10 metrics)
         |
         | snowflake-connector-python
         v
[Streamlit Dashboard]
   - Device activity map (pydeck)
   - AQI time-series (plotly)
   - Top devices by AQI (bar chart)
   - 30s auto-refresh
```

## VPC Layout

```
VPC: 10.0.0.0/16  (us-east-1)
|
|-- Public Subnet 10.0.1.0/24  (us-east-1a) -- Bastion EC2, NAT Gateway
|-- Public Subnet 10.0.2.0/24  (us-east-1b)
|
|-- Private Subnet 10.0.11.0/24 (us-east-1a) -- PostgreSQL, Kafka Connect, MSK broker 1
|-- Private Subnet 10.0.12.0/24 (us-east-1b) -- MSK broker 2

Security Groups:
- bastion-sg:       no inbound, outbound all
- postgres-sg:      5432 from connect-sg + bastion-sg
- kafka-connect-sg: 8083 from bastion-sg, outbound all
- msk-sg:           9092/9094 from kafka-connect-sg

VPC Endpoints (private):
- SSM, SSMMessages, EC2Messages  --> Bastion SSM access
- SecretsManager                 --> PG + Connect fetch credentials
```

## CDK Stack Dependency Order

```
HygieneStack  (independent)
VpcStack      (independent)
S3Stack       (independent)
MskStack      --> depends on VpcStack
Ec2Stack      --> depends on VpcStack
IotStack      --> depends on VpcStack + MskStack
```
