from aws_cdk import (
    NestedStack,
    aws_lambda as _lambda,
    aws_iam as _iam,
    Duration,
    custom_resources as cr,
)
from aws_cdk.aws_logs import RetentionDays

from constructs import Construct
import os
from post_stack.constant import *

class ServicePostStack(NestedStack):
    account_id = None
    region = None

    s3_web_bucket_name = None
    s3_data_bucket_name = None
    user_emails = None
    cognito_user_pool_id = None
    cognito_app_client_id = None
    cloudfront_url = None

    cognito_user_name = None
    cognito_user_pwd = None

    def __init__(self, scope: Construct, construct_id: str, 
                cognito_user_pool_id, 
                cognito_app_client_id, 
                user_emails, 
                s3_web_bucket_name,
                s3_data_bucket_name,
                cloudfront_url,
                cognito_user_name,
                cognito_user_pwd,
                **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")

        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_app_client_id = cognito_app_client_id
        self.user_emails = user_emails
        self.s3_web_bucket_name = s3_web_bucket_name
        self.s3_data_bucket_name = s3_data_bucket_name
        self.cloudfront_url = cloudfront_url

        self.cognito_user_name = cognito_user_name
        self.cognito_user_pwd = cognito_user_pwd
        
        self.deploy_custom_res() # Cognito user and send invitation email

    def deploy_custom_res(self):
        # Custom Resource Lambda: provision-custom-resource
        # Add user to the Cognito user pool and send invitation email
        lambda_post_provision_role = _iam.Role(
            self, "UtilPostProvisionLambdaRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"util-post-provision-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["cognito-idp:AdminCreateUser","cognito-idp:UpdateUserPool","cognito-idp:UpdateUserPool","cognito-idp:AdminSetUserPassword"],
                        resources=[f"arn:aws:cognito-idp:{self.region}:{self.account_id}:userpool/{self.cognito_user_pool_id}"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject", "s3:PutBucketCors", "s3:GetBucketCors"],
                        resources=[
                            f"arn:aws:s3:::{self.s3_web_bucket_name}",
                            f"arn:aws:s3:::{self.s3_web_bucket_name}/*",
                            f"arn:aws:s3:::{self.s3_data_bucket_name}",
                            f"arn:aws:s3:::{self.s3_data_bucket_name}/*",
                        ]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["cloudfront:CreateInvalidation"],
                        resources=[f"arn:aws:cloudfront::{self.account_id}:distribution/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sagemaker:DescribeNotebookInstance"],
                        resources=[f"arn:aws:sagemaker:{self.region}:{self.account_id}:notebook-instance/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/{LAMBDA_NAME_PREFIX}util-post-provision:*"]
                    ),
                ]
            )}
        )
        lambda_provision = _lambda.Function(self, 
            id='util-post-provision-lambda', 
            function_name=f"{LAMBDA_NAME_PREFIX}util-post-provision", 
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler='util-post-provision.on_event',
            code=_lambda.Code.from_asset(os.path.join("../deployment/post_stack", "./lambda/util-post-provision")),
            timeout=Duration.seconds(120),
            role=lambda_post_provision_role,
            memory_size=512,
            environment={
             'COGNITO_USER_POOL_ID': self.cognito_user_pool_id,
             'COGNITO_USER_POOL_CLIENT_ID': self.cognito_app_client_id,
             'COGNITO_REGION': self.region,
             'COGNITO_USER_EMAILS': self.user_emails,
             'COGNITO_INVITATION_EMAIL_TEMPLATE': COGNITO_INVITATION_EMAIL_TEMPLATE,
             'COGNITO_INVITATION_EMAIL_TITLE': COGNITO_INVITATION_EMAIL_TITLE,
             'CLOUD_FRONT_URL': self.cloudfront_url,
             'APP_NAME': APP_NAME,
             'S3_BUCKET_NAME_STAGING': self.s3_data_bucket_name,
             'S3_BUCKET_NAME_WEB': self.s3_web_bucket_name,
             'COGNITO_USER_NAME': self.cognito_user_name,
             'COGNITO_USER_PWD': self.cognito_user_pwd
            }
        )
        
        lambda_post_provision_invoke_role = _iam.Role(
            self, "UtilPostProvisionCustomResRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"util-post-provison-custom-res-policy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction", "lambda:InvokeAsync"],
                        resources=[lambda_provision.function_arn],
                    )
                ]
            )}
        )
        c_resource = cr.AwsCustomResource(
            self,
            f"srv-post-provision-web-provider",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=cr.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": "{\"RequestType\": \"Create\"}"
                },
                output_paths=["Payload"]
            ),
            role=lambda_post_provision_invoke_role
        )     
