from aws_cdk import (
    NestedStack,
    aws_s3 as _s3,
    aws_lambda as _lambda,
    aws_iam as _iam,
    Duration,
    RemovalPolicy,
    custom_resources,
    aws_cognito as _cognito,
    Size
)
from aws_cdk.aws_logs import RetentionDays
from aws_cdk.aws_apigateway import IdentitySource

from constructs import Construct
import os
import json
from pre_stack.constant import *

class ServicePreStack(NestedStack):
    account_id = None
    region = None

    s3_data_bucket_name = None

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.deploy_s3() # S3 data bucket
        self.deploy_cognito()
        self.deploy_provision() # Lambda Layers, S3 vectors

    def deploy_s3(self):
        # Create data S3 bucket
        self.s3_bucket_name_data = f'{S3_BUCKET_DATA_PREFIX}-{self.account_id}-{self.region}'
        s3_data_bucket = _s3.Bucket(self, "DataBucket", 
            bucket_name=self.s3_bucket_name_data,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_prefix="access-log/",
            enforce_ssl=True,
            event_bridge_enabled=True,  # Enable EventBridge notifications
            cors=[_s3.CorsRule(
                allowed_methods=[_s3.HttpMethods.GET, _s3.HttpMethods.POST, _s3.HttpMethods.PUT, _s3.HttpMethods.DELETE, _s3.HttpMethods.HEAD],
                allowed_origins=["*"],
                allowed_headers=["*"],
                exposed_headers=["ETag"],
                max_age=3000
            )])
        self.s3_data_bucket_name = s3_data_bucket.bucket_name

    def deploy_cognito(self):
        # Create Cognitio User pool and authorizer
        user_pool = _cognito.UserPool(self, "WebUserPool",
            user_pool_name=f"{COGNITO_NAME_PREFIX}-user-pool",
            self_sign_up_enabled=False,
            password_policy=_cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(7)
            ),
            #advanced_security_mode=_cognito.AdvancedSecurityMode.ENFORCED,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.cognito_user_pool_id = user_pool.user_pool_id

        web_client = user_pool.add_client("AppClient", 
            auth_flows=_cognito.AuthFlow(
                user_password=True,
                user_srp=True
            ),
            supported_identity_providers=[_cognito.UserPoolClientIdentityProvider.COGNITO],
        )
        self.cognito_app_client_id = web_client.user_pool_client_id

        # Identity pool
        identity_pool = _cognito.CfnIdentityPool(
            self,
            "AppIdentityPool",
            identity_pool_name=f"{COGNITO_NAME_PREFIX}-identity-pool",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                _cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=web_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name,
                )
            ],
        )

        # --- IAM Roles for Authenticated and Unauthenticated users ---
        authenticated_role = _iam.Role(
            self,
            "CognitoAuthenticatedRole",
            assumed_by=_iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonCognitoPowerUser")
            ],
            inline_policies={f"{COGNITO_NAME_PREFIX}-identity-pool-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock-agentcore:InvokeAgentRuntime"],
                        resources=[
                            f"arn:aws:bedrock-agentcore:{self.region}:{self.account_id}:runtime/{AGENTCORE_RUNTIME_NAME_PREFIX}*",
                            f"arn:aws:bedrock-agentcore:{self.region}:{self.account_id}:runtime/{AGENTCORE_RUNTIME_NAME_PREFIX}*/runtime-endpoint/*"
                        ]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["cognito-identity:GetCredentialsForIdentity"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:*"]
                    ),
                ]
            )},
        )

        unauthenticated_role = _iam.Role(
            self,
            "CognitoUnauthenticatedRole",
            assumed_by=_iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "unauthenticated"
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )

        # --- Attach roles to Identity Pool ---
        _cognito.CfnIdentityPoolRoleAttachment(
            self,
            "IdentityPoolRoleAttachment",
            identity_pool_id=identity_pool.ref,
            roles={
                "authenticated": authenticated_role.role_arn,
                "unauthenticated": unauthenticated_role.role_arn,
            },
        )

        self.cognito_identity_pool_id = identity_pool.ref

    def deploy_provision(self):

        aws_layer = _lambda.LayerVersion.from_layer_version_arn(self, "AwsLayerPowerTool", 
            layer_version_arn=f"arn:aws:lambda:{self.region}:017000801446:layer:AWSLambdaPowertoolsPythonV2:68"
        )

        # Custom Resource Lambda: util-pre-provision
        # Build lambda layer zip files
        lambda_key = "util-pre-provision"
        lambda_util_provision_role = _iam.Role(
            self, "UtilPreLambdaProvisionRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={f"{lambda_key}-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_data}",f"arn:aws:s3:::{self.s3_bucket_name_data}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["iam:CreateRole", "iam:CreateServiceLinkedRole","iam:GetRole"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3vectors:*"],
                        resources=[f"arn:aws:s3vectors:{self.region}:{self.account_id}:bucket/{S3_VECTOR_BUCKET_NAME}*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/{LAMBDA_NAME_PREFIX}{lambda_key}:*"]
                    ),
                ]
            )},
        )
        lambda_util_provision = _lambda.Function(self, 
            id=f'util-pre-provision_function', 
            function_name=f"{LAMBDA_NAME_PREFIX}{lambda_key}", 
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler='util-pre-provision.on_event',
            code=_lambda.Code.from_asset(os.path.join("../deployment/pre_stack", f"./lambda/{lambda_key}")),
            timeout=Duration.minutes(15),
            role=lambda_util_provision_role,
            memory_size=10240,
            ephemeral_storage_size=Size.mebibytes(10240),
            layers=[aws_layer]
        )
        

        lambda_util_provision_invoke_role = _iam.Role(
            self, "UtilPreLambdaProvisionInvokeRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"util-pre-provision-invoke-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["ec2:DescribeInstances", "ec2:CreateNetworkInterface", "ec2:AttachNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction", "lambda:InvokeAsync"],
                        resources=[lambda_util_provision.function_arn],
                    )
                ]
            )}
        )

        # 1 invoke: scenedetect, S3 vectors
        c_resource = custom_resources.AwsCustomResource(self,
            id=f"util-pre-provision-invoke-res",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_util_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps(
                        {
                            "RequestType":"Create",
                            "Layers": [
                                {
                                    "name": "scenedetect_layer",
                                    "packages": [
                                        {
                                            "name":"scenedetect",
                                            "version":"0.6.7.1"
                                        },
                                        {
                                            "name": "opencv-python-headless",
                                            "version": "4.12.0.88"
                                        },
                                        {
                                            "name": "numpy",
                                            "version": "2.2.6"
                                        }
                                    ],
                                    "s3_bucket":self.s3_data_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_SCENE_DETECT
                                },  
                            ],
                            "S3Vectors": [
                                {
                                    "BucketName": S3_VECTOR_BUCKET_NAME,
                                    "IndexName": S3_VECTOR_INDEX_NAME,
                                    "IndexDim": EMBEDDING_DIM_DEFAULT_NOVA_MME
                                },
                                {
                                    "BucketName": S3_VECTOR_BUCKET_NAME,
                                    "IndexName": S3_VECTOR_INDEX_NOVA_MME_FIXED,
                                    "IndexDim": EMBEDDING_DIM_DEFAULT_NOVA_MME
                                },
                                {
                                    "BucketName": S3_VECTOR_BUCKET_NAME,
                                    "IndexName": S3_VECTOR_INDEX_TLABS_27,
                                    "IndexDim": EMBEDDING_DIM_DEFAULT_27
                                },
                                {
                                    "BucketName": S3_VECTOR_BUCKET_NAME,
                                    "IndexName": S3_VECTOR_INDEX_TLABS_30,
                                    "IndexDim": EMBEDDING_DIM_DEFAULT_30
                                }
                            ]
                        }
                    )
                },
                output_paths=["Payload"]
            ),
            role=lambda_util_provision_invoke_role
        )    

        # 2nd invoke: opencv
        resource = custom_resources.AwsCustomResource(self,
            id=f"util-pre-provision-invoke-res2",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_util_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps(
                        {
                            "RequestType":"Create",
                            "Layers": [
                                {
                                    "name": "opencv",
                                    "packages": [
                                        {
                                            "name":"opencv-python-headless",
                                            "version":"4.12.0.88",
                                        }
                                    ],
                                    "s3_bucket":self.s3_data_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_OPENCV
                                }
                            ]
                        }
                    )
                },
                output_paths=["Payload"]
            ),
            role=lambda_util_provision_invoke_role
        )    

        # 3nd invoke: boto3
        resource = custom_resources.AwsCustomResource(self,
            id=f"util-pre-provision-invoke-res3",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_util_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps(
                        {
                            "RequestType":"Create",
                            "Layers": [
                                {
                                    "name": "boto3",
                                    "packages": [
                                        {
                                            "name":"boto3",
                                            "version":"1.40.15",
                                        }
                                    ],
                                    "s3_bucket":self.s3_data_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_BOTO3
                                },
                            ]
                        }
                    )
                },
                output_paths=["Payload"]
            ),
            role=lambda_util_provision_invoke_role
        )    

        # 4th invoke: moviepy
        resource = custom_resources.AwsCustomResource(self,
            id=f"util-pre-provision-invoke-res4",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_util_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps(
                        {
                            "RequestType":"Create",
                            "Layers": [
                                {
                                    "name": "moviepy",
                                    "packages": [
                                        {
                                            "name":"moviepy",
                                            "version":"2.2.1",
                                        }
                                    ],
                                    "s3_bucket":self.s3_data_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_MOVIEPY
                                },
                            ]
                        }
                    )
                },
                output_paths=["Payload"]
            ),
            role=lambda_util_provision_invoke_role
        )    