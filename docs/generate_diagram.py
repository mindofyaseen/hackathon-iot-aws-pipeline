"""
Run: pip install diagrams && python docs/generate_diagram.py
Outputs: docs/architecture_phase1.png, docs/architecture_phase2.png
"""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.iot import IotCore
from diagrams.aws.analytics import ManagedStreamingForKafka as MSK
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3
from diagrams.aws.network import VPC, NATGateway
from diagrams.aws.management import SystemsManagerStateManager as SSM
from diagrams.aws.security import SecretsManager
from diagrams.saas.analytics import Snowflake
from diagrams.programming.language import Python
from diagrams.onprem.analytics import Dbt


graph_attr = {"fontsize": "14", "bgcolor": "white", "pad": "0.5"}


with Diagram(
    "Phase 1 -- IoT Ingestion and On-Prem Simulation",
    filename="docs/architecture_phase1",
    outformat="png",
    graph_attr=graph_attr,
    direction="LR",
    show=False,
):
    simulator = Python("IoT Simulator\n5 Devices")

    with Cluster("AWS Cloud"):
        iot = IotCore("AWS IoT Core\niot/sensors/#")

        with Cluster("VPC us-east-1"):
            nat = NATGateway("NAT GW")
            ssm = SSM("SSM\nSession Manager")

            with Cluster("Private Subnets"):
                msk = MSK("MSK Kafka\niot-events\nkafka.t3.small x2")
                connect = EC2("Kafka Connect\nt3.small")
                postgres = EC2("PostgreSQL EC2\nt3.medium\nwal_level=logical")

            with Cluster("Public Subnet"):
                bastion = EC2("Bastion\nt3.micro")

        s3 = S3("S3 Backup\n30-day lifecycle")
        secret = SecretsManager("Secrets Manager\nPG credentials")

    simulator >> Edge(label="MQTT") >> iot
    iot >> Edge(label="Kafka Action\nVPC Dest") >> msk
    msk >> Edge(label="JDBC Sink") >> connect >> postgres
    msk >> Edge(label="S3 Sink\n(optional)") >> s3
    ssm >> bastion >> postgres
    secret >> connect


with Diagram(
    "Phase 2 -- CDC Migration to Snowflake",
    filename="docs/architecture_phase2",
    outformat="png",
    graph_attr=graph_attr,
    direction="LR",
    show=False,
):
    with Cluster("AWS -- Phase 1 Output"):
        postgres = EC2("PostgreSQL\nWAL logical")
        msk = MSK("MSK Kafka\ncdc.public.iot_events")
        connect = EC2("Kafka Connect\nDebezium")

    with Cluster("Snowflake HACKATHON_IOT"):
        raw = Snowflake("RAW.IOT_EVENTS\nBronze (VARIANT)")
        silver = Snowflake("CLEAN.STG_IOT_EVENTS\nSilver (parsed)")
        gold = Snowflake("ANALYTICS.AGG_DEVICE_DAILY\nGold (aggregated)")

    dbt_node = Dbt("dbt\nrun + test")
    dashboard = Python("Streamlit\nDashboard")

    postgres >> Edge(label="Debezium\nCDC") >> connect
    connect >> msk
    msk >> Edge(label="Snowflake\nKafka Connector") >> raw
    raw >> dbt_node >> silver >> dbt_node >> gold
    gold >> dashboard


print("Diagrams generated: docs/architecture_phase1.png, docs/architecture_phase2.png")
