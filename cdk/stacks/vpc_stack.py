from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class VpcStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "HackathonVpc",
            vpc_name="hackathon-iot-vpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24
                ),
            ],
        )

        self.vpc.add_interface_endpoint(
            "SsmEndpoint", service=ec2.InterfaceVpcEndpointAwsService.SSM
        )
        self.vpc.add_interface_endpoint(
            "SsmMessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        )
        self.vpc.add_interface_endpoint(
            "Ec2MessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
        )
        self.vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
        )

        self.msk_sg = ec2.SecurityGroup(
            self, "MskSg", vpc=self.vpc, description="MSK Kafka cluster", security_group_name="hackathon-msk-sg"
        )
        self.connect_sg = ec2.SecurityGroup(
            self, "ConnectSg", vpc=self.vpc, description="Kafka Connect EC2", security_group_name="hackathon-connect-sg"
        )
        self.postgres_sg = ec2.SecurityGroup(
            self, "PostgresSg", vpc=self.vpc, description="PostgreSQL EC2", security_group_name="hackathon-postgres-sg"
        )
        self.bastion_sg = ec2.SecurityGroup(
            self, "BastionSg", vpc=self.vpc, description="Bastion host (SSM only)", security_group_name="hackathon-bastion-sg"
        )

        self.msk_sg.add_ingress_rule(
            self.connect_sg, ec2.Port.tcp(9092), "Kafka Connect to MSK plaintext"
        )
        self.msk_sg.add_ingress_rule(
            self.connect_sg, ec2.Port.tcp(9094), "Kafka Connect to MSK TLS"
        )
        self.postgres_sg.add_ingress_rule(
            self.connect_sg, ec2.Port.tcp(5432), "Kafka Connect to PostgreSQL"
        )
        self.postgres_sg.add_ingress_rule(
            self.bastion_sg, ec2.Port.tcp(5432), "Bastion to PostgreSQL"
        )
        self.connect_sg.add_ingress_rule(
            self.bastion_sg, ec2.Port.tcp(8083), "Bastion to Kafka Connect REST API"
        )

        CfnOutput(self, "VpcId", value=self.vpc.vpc_id, export_name="HackathonVpcId")
        CfnOutput(
            self,
            "PrivateSubnetIds",
            value=",".join([s.subnet_id for s in self.vpc.private_subnets]),
            export_name="HackathonPrivateSubnetIds",
        )
