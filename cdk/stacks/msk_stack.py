from aws_cdk import (
    Stack,
    aws_msk as msk,
    aws_ssm as ssm,
    custom_resources as cr,
    CfnOutput,
)
from constructs import Construct


class MskStack(Stack):
    def __init__(self, scope, construct_id, vpc_stack, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        vpc = vpc_stack.vpc
        msk_sg = vpc_stack.msk_sg

        self.cluster = msk.CfnCluster(
            self,
            "HackathonMsk",
            cluster_name="hackathon-iot-msk",
            kafka_version="3.6.0",
            number_of_broker_nodes=2,
            broker_node_group_info=msk.CfnCluster.BrokerNodeGroupInfoProperty(
                instance_type="kafka.t3.small",
                client_subnets=[s.subnet_id for s in vpc.private_subnets],
                security_groups=[msk_sg.security_group_id],
                storage_info=msk.CfnCluster.StorageInfoProperty(
                    ebs_storage_info=msk.CfnCluster.EBSStorageInfoProperty(
                        volume_size=20
                    )
                ),
            ),
            encryption_info=msk.CfnCluster.EncryptionInfoProperty(
                encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                    client_broker="PLAINTEXT",
                    in_cluster=True,
                )
            ),
            enhanced_monitoring="DEFAULT",
            client_authentication=msk.CfnCluster.ClientAuthenticationProperty(
                unauthenticated=msk.CfnCluster.UnauthenticatedProperty(enabled=True)
            ),
        )

        ssm.StringParameter(
            self,
            "MskClusterArnParam",
            parameter_name="/hackathon/msk/cluster-arn",
            string_value=self.cluster.ref,
        )

        # MSK bootstrap brokers are not a CloudFormation output -- must call
        # the Kafka API after the cluster is ACTIVE. AwsCustomResource runs a
        # Lambda post-create to fetch and surface the broker string.
        get_brokers = cr.AwsCustomResource(
            self,
            "GetMskBrokers",
            install_latest_aws_sdk=False,
            on_create=cr.AwsSdkCall(
                service="Kafka",
                action="getBootstrapBrokers",
                parameters={"ClusterArn": self.cluster.ref},
                physical_resource_id=cr.PhysicalResourceId.of(self.cluster.ref),
                output_paths=["BootstrapBrokerString"],
            ),
            on_update=cr.AwsSdkCall(
                service="Kafka",
                action="getBootstrapBrokers",
                parameters={"ClusterArn": self.cluster.ref},
                physical_resource_id=cr.PhysicalResourceId.of(self.cluster.ref),
                output_paths=["BootstrapBrokerString"],
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
        )
        get_brokers.node.add_dependency(self.cluster)

        self.bootstrap_brokers = get_brokers.get_response_field("BootstrapBrokerString")

        ssm.StringParameter(
            self,
            "MskBootstrapBrokersParam",
            parameter_name="/hackathon/msk/bootstrap-brokers",
            string_value=self.bootstrap_brokers,
        )

        CfnOutput(self, "MskClusterArn", value=self.cluster.ref, export_name="HackathonMskClusterArn")
        CfnOutput(self, "MskBootstrapBrokers", value=self.bootstrap_brokers, export_name="HackathonMskBrokers")
