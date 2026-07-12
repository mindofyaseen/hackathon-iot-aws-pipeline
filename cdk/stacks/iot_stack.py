from aws_cdk import (
    Stack,
    aws_iot as iot,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct


class IotStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, vpc_stack, msk_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = vpc_stack.vpc
        connect_sg = vpc_stack.connect_sg

        # IAM role for IoT Core to create VPC network interfaces
        # Inline policy in constructor so role + policy are one CF resource (avoids IAM propagation race)
        iot_vpc_role = iam.Role(
            self,
            "IotVpcRole",
            assumed_by=iam.ServicePrincipal("iot.amazonaws.com"),
            description="Allows IoT Core to create VPC network interfaces for MSK access",
            inline_policies={
                "IotVpcNetworkPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "ec2:CreateNetworkInterface",
                                "ec2:DescribeNetworkInterfaces",
                                "ec2:DescribeVpcs",
                                "ec2:DeleteNetworkInterface",
                                "ec2:DescribeSubnets",
                                "ec2:DescribeVpcAttribute",
                                "ec2:DescribeSecurityGroups",
                            ],
                            resources=["*"],
                        )
                    ]
                )
            },
        )

        # IoT VPC destination -- lets IoT Core reach MSK in private subnet
        vpc_destination = iot.CfnTopicRuleDestination(
            self,
            "IotVpcDestination",
            vpc_properties=iot.CfnTopicRuleDestination.VpcDestinationPropertiesProperty(
                vpc_id=vpc.vpc_id,
                subnet_ids=[s.subnet_id for s in vpc.private_subnets],
                security_groups=[connect_sg.security_group_id],
                role_arn=iot_vpc_role.role_arn,
            ),
            status="ENABLED",
        )

        # IAM role for IoT Core to write to MSK
        iot_msk_role = iam.Role(
            self,
            "IotToMskRole",
            assumed_by=iam.ServicePrincipal("iot.amazonaws.com"),
            description="Allows IoT Core rule to publish to MSK iot-events topic",
        )
        iot_msk_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kafka-cluster:Connect",
                    "kafka-cluster:DescribeTopic",
                    "kafka-cluster:WriteData",
                ],
                resources=[
                    msk_stack.cluster.ref,
                    f"{msk_stack.cluster.ref}/topic/iot-events",
                ],
            )
        )

        # IoT Core rule: MQTT iot/sensors/# -> MSK iot-events topic
        iot.CfnTopicRule(
            self,
            "IotToMskRule",
            rule_name="iot_events_to_msk",
            topic_rule_payload=iot.CfnTopicRule.TopicRulePayloadProperty(
                sql="SELECT *, topic() AS mqtt_topic, timestamp() AS ingest_ts FROM 'iot/sensors/#'",
                aws_iot_sql_version="2016-03-23",
                actions=[
                    iot.CfnTopicRule.ActionProperty(
                        kafka=iot.CfnTopicRule.KafkaActionProperty(
                            destination_arn=vpc_destination.attr_arn,
                            topic="iot-events",
                            client_properties={
                                "bootstrap.servers": msk_stack.bootstrap_brokers,
                                "security.protocol": "PLAINTEXT",
                            },
                        )
                    )
                ],
                rule_disabled=False,
            ),
        )

        # IoT Thing type for geoLocation devices
        iot.CfnThingType(
            self,
            "GeoLocationThingType",
            thing_type_name="geoLocation",
            thing_type_properties=iot.CfnThingType.ThingTypePropertiesProperty(
                thing_type_description="Simulated IoT sensor publishing location and environmental telemetry",
                searchable_attributes=["device_id", "location"],
            ),
        )

        CfnOutput(self, "IotMskRoleArn", value=iot_msk_role.role_arn, export_name="HackathonIotMskRoleArn")
        CfnOutput(self, "IotVpcDestinationArn", value=vpc_destination.attr_arn, export_name="HackathonIotVpcDest")
