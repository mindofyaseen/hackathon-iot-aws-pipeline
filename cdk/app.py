import os
import aws_cdk as cdk
from stacks.hygiene_stack import HygieneStack
from stacks.vpc_stack import VpcStack
from stacks.s3_stack import S3Stack
from stacks.msk_stack import MskStack
from stacks.ec2_stack import Ec2Stack
from stacks.iot_stack import IotStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT", "989864147584"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

hygiene = HygieneStack(app, "HygieneStack", env=env)
vpc = VpcStack(app, "VpcStack", env=env)
s3 = S3Stack(app, "S3Stack", env=env)
msk = MskStack(app, "MskStack", vpc_stack=vpc, env=env)
ec2 = Ec2Stack(app, "Ec2Stack", vpc_stack=vpc, env=env)
iot = IotStack(app, "IotStack", vpc_stack=vpc, msk_stack=msk, env=env)

msk.add_dependency(vpc)
ec2.add_dependency(vpc)
iot.add_dependency(msk)
iot.add_dependency(vpc)

app.synth()
