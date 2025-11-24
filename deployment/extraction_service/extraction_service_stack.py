from aws_cdk import (
    NestedStack,
    Size,
    aws_ec2 as ec2,
    aws_cognito as _cognito,
    aws_s3 as _s3,
    aws_lambda as _lambda,
    aws_apigateway as _apigw,
    aws_iam as _iam,
    aws_dynamodb as _dynamodb,
    Duration,
    aws_stepfunctions as _aws_stepfunctions,
    RemovalPolicy,
    custom_resources as cr,
    aws_logs as logs,
)
from aws_cdk.aws_apigateway import IdentitySource

from constructs import Construct
import os, re
from extraction_service.constant import *

class ExtrServiceStack(NestedStack):
    account_id = None
    region = None
    api_gw_base_url = None
    cognito_user_pool_id = None
    cognito_app_client_id = None
    s3_bucket_name_extraction = None

    s3_extraction_bucket = None

    scenedetect_layer = None
    moviepy_layer = None
    opencv_layer = None
    aws_layer = None

    cognito_authorizer = None

    api = None
    
    def __init__(self, scope: Construct, construct_id: str, 
                 s3_bucket_name_extraction: str, cognito_user_pool_id: str, cognito_app_client_id: str, 
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.s3_bucket_name_extraction = s3_bucket_name_extraction
        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_app_client_id = cognito_app_client_id

        self.deploy_dynamodb()
        self.deploy_cognito()
        self.deploy_lambda_layer()
        self.deploy_step_function()
        self.deploy_apigw()

    def deploy_dynamodb(self):
        # Create DynamoDB tables
        # Video task table                           
        video_task_table = _dynamodb.Table(self, 
            id='video-task-table', 
            table_name=DYNAMO_VIDEO_TASK_TABLE, 
            partition_key=_dynamodb.Attribute(name='Id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        video_task_table.add_global_secondary_index(
            index_name="RequestBy-index",
            partition_key=_dynamodb.Attribute(
                name="RequestBy",
                type=_dynamodb.AttributeType.STRING
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        # Video transcription table
        video_trans_table = _dynamodb.Table(self, 
            id='video-trans-table', 
            table_name=DYNAMO_VIDEO_TRANS_TABLE, 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        ) 
        video_trans_table.add_global_secondary_index(
            index_name="task_id-start_ts-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="start_ts",
                type=_dynamodb.AttributeType.NUMBER
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        # Video frame table
        video_frame_table = _dynamodb.Table(self, 
            id='video-frame-table', 
            table_name=DYNAMO_VIDEO_FRAME_TABLE, 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        ) 
        video_frame_table.add_global_secondary_index(
            index_name="task_id-timestamp-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="timestamp",
                type=_dynamodb.AttributeType.NUMBER
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        # Video shot table
        video_shot_table = _dynamodb.Table(self, 
            id='video-shot-table', 
            table_name=DYNAMO_VIDEO_SHOT_TABLE, 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        ) 
        video_shot_table.add_global_secondary_index(
            index_name="task_id-analysis_type-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="analysis_type",
                type=_dynamodb.AttributeType.STRING
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        video_shot_table.add_global_secondary_index(
            index_name="task_id-index-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="index",
                type=_dynamodb.AttributeType.NUMBER
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        
        # Video usage table
        video_usage_table = _dynamodb.Table(self, 
            id='video-usage-table', 
            table_name=DYNAMO_VIDEO_USAGE_TABLE, 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        video_usage_table.add_global_secondary_index(
            index_name="task_id-type-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="type",
                type=_dynamodb.AttributeType.STRING
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )

    def deploy_cognito(self):
        user_pool = _cognito.UserPool.from_user_pool_id(
            self, "WebUserPool",
            user_pool_id=self.cognito_user_pool_id
        )

        #self.cognito_user_pool_id = user_pool.user_pool_id
        web_client = _cognito.UserPoolClient.from_user_pool_client_id(
            self, "NovaMmSrvAppClient",
            user_pool_client_id=self.cognito_app_client_id
        )

        # Create API Gateway CognitioUeserPoolAuthorizer
        self.cognito_authorizer = _apigw.CognitoUserPoolsAuthorizer(self, f"ExtrSrvWebAuth", 
            cognito_user_pools=[user_pool],
            identity_source=IdentitySource.header('Authorization')
        )

    def deploy_lambda_layer(self):
        # Create Lambda Layers which will be used by Lambda deployment
        layer_bucket = _s3.Bucket.from_bucket_name(self, "LayerBucket", bucket_name=self.s3_bucket_name_extraction)
        self.scenedetect_layer = _lambda.LayerVersion(self, 'SceneLayer',
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_SCENE_DETECT),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_13],
            description="python3.13 scenedetect 0.6.7.1, opencv-python-headless 4.12.0.88, numpy 2.2.6"
        )
        self.moviepy_layer = _lambda.LayerVersion(self, 'MoviePyLayer',
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_MOVIEPY),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_13],
            description="python3.13 moviepy 2.2.1"
        )
        self.opencv_layer = _lambda.LayerVersion(self, 'OpenCvPyLayer',
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_OPENCV),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_13],
            description="python3.13 opencv-python-headless 4.12.0.88"
        )
        self.aws_layer = _lambda.LayerVersion.from_layer_version_arn(self, "AwsLayerPowerTool", 
            layer_version_arn=f"arn:aws:lambda:{self.region}:336392948345:layer:AWSSDKPandas-Python313:4"
        )

    def deploy_step_function(self):
        # Step Function - start
        # Lambda: extr-srv-wf-frame-video-metadata
        lambda_key = "extr-srv-wf-frame-video-metadata"
        lambda_extration_srv_metadata_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        lambda_extr_srv_fw_frame_metadata = self.create_lambda(
            lambda_key, 
            lambda_extration_srv_metadata_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'MODEL_ID_IMAGE_UNDERSTANDING': MODEL_ID_IMAGE_UNDERSTANDING,
                'VIDEO_SAMPLE_CHUNK_DURATION_S': VIDEO_SAMPLE_CHUNK_DURATION_S,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE
            }, 
            timeout_s=15*60, memory_size=10240, ephemeral_storage_size=10240,
            layers=[self.moviepy_layer]
        )

        # Lambda: extr-srv-wf-frame-sample-video
        lambda_key = "extr-srv-wf-frame-sample-video"
        lambda_extration_srv_wf_frame_sample_video_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        lambda_extr_srv_fw_frame_sample_video = self.create_lambda(
            lambda_key, 
            lambda_extration_srv_wf_frame_sample_video_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'VIDEO_SAMPLE_CHUNK_DURATION_S': VIDEO_SAMPLE_CHUNK_DURATION_S,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
            }, 
            timeout_s=15*60, memory_size=10240, ephemeral_storage_size=10240,
            layers=[self.moviepy_layer]
        )

        # Lambda: extr-srv-fw-frame-sample-dedup-mme
        lambda_key = "extr-srv-fw-frame-sample-dedup-mme"
        lambda_extration_srv_fw_frame_dedup_mme_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        lambda_extr_srv_wf_frame_sample_dedup_mme = self.create_lambda(
            lambda_key, 
            lambda_extration_srv_fw_frame_dedup_mme_role, 
            {
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'VIDEO_FRAME_SIMILAIRTY_THRESHOLD': VIDEO_FRAME_SIMILAIRTY_THRESHOLD_DEFAULT_MME,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'BEDROCK_MME_MODEL_ID': MODEL_ID_BEDROCK_MME,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE
            }, 
            timeout_s=300, memory_size=10240, ephemeral_storage_size=1024,
            layers=[self.aws_layer],
        )

        # Lambda: extr-srv-fw-frame-sample-dedup-orb
        lambda_key = "extr-srv-fw-frame-sample-dedup-orb"
        lambda_extration_srv_fw_frame_dedup_orb_role = self.create_role(lambda_key, ["s3","dynamodb"])
        lambda_extr_srv_wf_frame_sample_dedup_orb = self.create_lambda(
            lambda_key, 
            lambda_extration_srv_fw_frame_dedup_orb_role, 
            {
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'VIDEO_FRAME_SIMILAIRTY_THRESHOLD_DEFAULT': VIDEO_FRAME_SIMILAIRTY_THRESHOLD_DEFAULT_ORB,
                'VIDEO_SAMPLE_FILE_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
            }, 
            timeout_s=60, memory_size=10240, ephemeral_storage_size=1024,
            layers=[self.opencv_layer],
        )

        # Lambda: extr-srv-wf-frame-extraction
        lambda_key = "extr-srv-wf-frame-extraction" 
        lambda_extr_srv_wf_frame_extraction_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        lambda_extr_srv_wf_frame_extraction = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_wf_frame_extraction_role, 
            {
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE
            }, 
            timeout_s=300, memory_size=1024, ephemeral_storage_size=1024,
            layers=[self.opencv_layer],
        )

        # Lambda: extr-srv-wf-start-transcribe
        lambda_key = "extr-srv-wf-start-transcribe" 
        lambda_extr_srv_wf_start_transcribe_role = self.create_role(lambda_key, ["dynamodb","transcribe","s3"])
        lambda_extr_srv_wf_start_transcribe = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_wf_start_transcribe_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'TRANSCRIBE_JOB_PREFIX': TRANSCRIBE_JOB_PREFIX,
                'TRANSCRIBE_OUTPUT_BUCKET': self.s3_bucket_name_extraction,
                'TRANSCRIBE_OUTPUT_PREFIX': TRANSCRIBE_OUTPUT_PREFIX
            }, 
            timeout_s=30,
        )

        # Lambda: extr-srv-wf-transcrip-post-process
        lambda_key = "extr-srv-wf-transcrip-post-process" 
        lambda_extr_srv_wf_transcrip_post_process_role = self.create_role(lambda_key, ["s3","dynamodb","transcribe"])
        lambda_extr_srv_wf_transcrip_post_process = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_wf_transcrip_post_process_role, 
            {             
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE
            }, 
            timeout_s=60*15, memory_size=10240, ephemeral_storage_size=10240,
        )
        
        # Lambda: extr-srv-fw-update-task-status
        lambda_key = "extr-srv-fw-update-task-status"
        lambda_extr_srv_fw_update_task_statu_role = self.create_role(lambda_key, ["dynamodb"])
        lambda_extr_srv_fw_update_task_status = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_fw_update_task_statu_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
            }, 
            timeout_s=10, memory_size=128, ephemeral_storage_size=512,
        )

        # Lambda: extr-srv-wf-clip-video-metadata
        lambda_key = "extr-srv-wf-clip-video-metadata"
        lambda_extration_srv_metadata_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        lambda_extr_srv_fw_clip_metadata = self.create_lambda(
            lambda_key, 
            lambda_extration_srv_metadata_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'MODEL_ID_IMAGE_UNDERSTANDING': MODEL_ID_IMAGE_UNDERSTANDING,
                'VIDEO_SAMPLE_CHUNK_DURATION_S': VIDEO_SAMPLE_CHUNK_DURATION_S,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE,
            }, 
            timeout_s=15*60, memory_size=10240, ephemeral_storage_size=10240,
            layers=[self.moviepy_layer]
        )

        # extr-srv-fw-clip-gen-shot-duration 
        lambda_key = "extr-srv-fw-clip-gen-shot-duration"
        lambda_extration_srv_metadata_role = self.create_role(lambda_key, ["s3","dynamodb"])
        lambda_extr_srv_fw_clip_gen_shot_durtion = self.create_lambda(
            lambda_key, 
            lambda_extration_srv_metadata_role, 
            {
                'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
            }, 
            timeout_s=15*60, memory_size=10240, ephemeral_storage_size=10240,
            layers=[self.scenedetect_layer],
        )
        
        # extr-srv-wf-clip-gen-shot-video 
        lambda_key = "extr-srv-wf-clip-gen-shot-video"
        lambda_extr_srv_wf_clip_gen_shot_video_role = self.create_role(lambda_key, ["s3","dynamodb"])
        lambda_extr_srv_wf_clip_gen_shot_video = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_wf_clip_gen_shot_video_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
            }, 
            timeout_s=15*60, memory_size=10240, ephemeral_storage_size=10240,
            layers=[self.moviepy_layer],
        )

        ## extr-srv-wf-clip-shot-understanding
        lambda_key = "extr-srv-wf-clip-shot-understanding"
        lambda_extr_srv_wf_clip_shot_understanding_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        lambda_extr_srv_fw_clip_shot_understanding = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_wf_clip_shot_understanding_role, 
            {
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
                'S3_BUCKET_DATA': self.s3_bucket_name_extraction,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE,
            }, 
            timeout_s=300, memory_size=4096, ephemeral_storage_size=4096,
            layers=[self.moviepy_layer],
        )

        # extr-srv-wf-clip-shot-embedding 
        lambda_key = "extr-srv-wf-clip-shot-embedding"
        lambda_extr_srv_wf_clip_shot_embed_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock","s3vectors"])
        lambda_extr_srv_wf_clip_shot_embed = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_wf_clip_shot_embed_role, 
            {
                'MME_MODEL_ID': MODEL_ID_BEDROCK_MME,
                'S3_VECTOR_BUCKET': S3_VECTOR_BUCKET_NAME, 
                'S3_VECTOR_INDEX':S3_VECTOR_INDEX_NAME,
                'EMBEDDING_DIM': EMBEDDING_DIM_DEFAULT,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'S3_BUCKET_DATA': self.s3_bucket_name_extraction,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE
            }, 
            timeout_s=30, memory_size=10240, ephemeral_storage_size=4096,
            layers=[self.moviepy_layer],
        )

        # StepFunctions 
        sf_key = "extr-srv-frame-based-flow"
        sm_frame_based_flow_json = None
        with open(f'../source/extraction_service/stepfunctions/{sf_key}/code.txt', "r") as f:
            sm_frame_based_flow_json = str(f.read())

        if sm_frame_based_flow_json is not None:
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_META_DATA##", lambda_extr_srv_fw_frame_metadata.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_SAMPLE_VIDEO##", lambda_extr_srv_fw_frame_sample_video.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_DEDUP_MME##", lambda_extr_srv_wf_frame_sample_dedup_mme.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_DEDUP_ORB##", lambda_extr_srv_wf_frame_sample_dedup_orb.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_EXTRACTION##", lambda_extr_srv_wf_frame_extraction.function_arn)
            #sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_SHOT_ANALYSIS##", lambda_extr_srv_wf_frame_shot_analysis.function_arn)
            #sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_FRAME_SHOT_SUMMARY##", lambda_extr_srv_fw_frame_shot_summary.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_START_TRANSCRIBE##", lambda_extr_srv_wf_start_transcribe.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_TRANSCRIPT_POST_PROCESS##", lambda_extr_srv_wf_transcrip_post_process.function_arn)
            sm_frame_based_flow_json = sm_frame_based_flow_json.replace("##LAMBDA_WF_UPADATE_TASK_STATUS##", lambda_extr_srv_fw_update_task_status.function_arn)
            
        extr_srv_frame_based_flow_role = _iam.Role(
            self, "ExtrSrvFrameFlowRole",
            assumed_by=_iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={f"{sf_key}-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["states:StartExecution","states:ListExecutions"],
                        resources=[f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:{STEP_FUNCTIONS_NAME_PREFIX}{sf_key}"]
                    ),
                     _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction"],
                        resources=[
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:{LAMBDA_NAME_PREFIX}extr-srv-*"
                        ]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"],
                        resources=[f"*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
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
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["transcribe:StartTranscriptionJob", "transcribe:DeleteTranscriptionJob","transcribe:GetTranscriptionJob"],
                        resources=["*"]
                    ),
                ]
            )}
        )
        self.sf_frame_based_flow = _aws_stepfunctions.StateMachine(self, f'{sf_key}',
            state_machine_name=f'{STEP_FUNCTIONS_NAME_PREFIX}{sf_key}', 
            definition_body=_aws_stepfunctions.DefinitionBody.from_string(sm_frame_based_flow_json),
            removal_policy=RemovalPolicy.DESTROY,
            role=extr_srv_frame_based_flow_role,
            timeout=Duration.hours(int(STEP_FUNCTIONS_FRAME_BASED_FLOW_TIMEOUT_HR)),
            tracing_enabled=True,
            logs= _aws_stepfunctions.LogOptions(
                destination=logs.LogGroup(self, f"/aws/vendedlogs/states/{sf_key}"),
                level=_aws_stepfunctions.LogLevel.ALL
            )
        )

        sf_key = "extr-srv-clip-based-flow"
        sm_clip_based_flow_json = None
        with open(f'../source/extraction_service/stepfunctions/{sf_key}/code.txt', "r") as f:
            sm_clip_based_flow_json = str(f.read())

        if sm_clip_based_flow_json is not None:
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_CLIP_METADATA##", lambda_extr_srv_fw_clip_metadata.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_CLIP_GEN_SHOT_DURATION##", lambda_extr_srv_fw_clip_gen_shot_durtion.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_CLIP_GEN_SHOT_VIDEO##", lambda_extr_srv_wf_clip_gen_shot_video.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_CLIP_SHOT_UNDERSTANDING##", lambda_extr_srv_fw_clip_shot_understanding.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_CLIP_SHOT_EMBED##", lambda_extr_srv_wf_clip_shot_embed.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_START_TRANSCRIBE##", lambda_extr_srv_wf_start_transcribe.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_TRANSCRIPT_POST_PROCESS##", lambda_extr_srv_wf_transcrip_post_process.function_arn)
            sm_clip_based_flow_json = sm_clip_based_flow_json.replace("##LAMBDA_WF_UPADATE_TASK_STATUS##", lambda_extr_srv_fw_update_task_status.function_arn)
            
        extr_srv_clip_based_flow_role = _iam.Role(
            self, "ExtrSrvCLipFlowRole",
            assumed_by=_iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={f"{sf_key}-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["states:StartExecution","states:ListExecutions"],
                        resources=[f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:{STEP_FUNCTIONS_NAME_PREFIX}{sf_key}"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sns:Publish"],
                        resources=[f"arn:aws:sns:{self.region}:{self.account_id}:*"]
                    ),
                     _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction"],
                        resources=[
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:{LAMBDA_NAME_PREFIX}extr-srv-*"
                        ]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"],
                        resources=[f"*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
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
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["transcribe:StartTranscriptionJob", "transcribe:DeleteTranscriptionJob","transcribe:GetTranscriptionJob"],
                        resources=["*"]
                    ),
                ]
            )}
        )
        self.sf_clip_based_flow = _aws_stepfunctions.StateMachine(self, f'{sf_key}',
            state_machine_name=f'{STEP_FUNCTIONS_NAME_PREFIX}{sf_key}', 
            definition_body=_aws_stepfunctions.DefinitionBody.from_string(sm_clip_based_flow_json),
            removal_policy=RemovalPolicy.DESTROY,
            role=extr_srv_clip_based_flow_role,
            timeout=Duration.hours(int(STEP_FUNCTIONS_CLIP_BASED_FLOW_TIMEOUT_HR)),
            tracing_enabled=True,
            logs= _aws_stepfunctions.LogOptions(
                destination=logs.LogGroup(self, f"/aws/vendedlogs/states/{sf_key}"),
                level=_aws_stepfunctions.LogLevel.ALL
            )
        )
        # Step Function - end

    def deploy_apigw(self):
        # API Gateway - start
        api = _apigw.RestApi(self, f"{API_NAME_PREFIX}Serice",
                                rest_api_name=f"{API_NAME_PREFIX}-service",
                                cloud_watch_role=True,
                                cloud_watch_role_removal_policy=RemovalPolicy.DESTROY,
                                deploy_options=_apigw.StageOptions(
                                        tracing_enabled=True,
                                        access_log_destination=_apigw.LogGroupLogDestination(logs.LogGroup(self, f"{API_NAME_PREFIX}ApiGatewayExtrSrvAccessLog")),
                                        access_log_format=_apigw.AccessLogFormat.clf(),
                                        method_options={
                                            "/*/*": _apigw.MethodDeploymentOptions( # This special path applies to all resource paths and all HTTP methods
                                                logging_level=_apigw.MethodLoggingLevel.INFO,)
                                    }                               
                                ),   
                            )

        # Create resources
        v1 = api.root.add_resource("v1")
        ex = v1.add_resource("extraction")
        ex_video = ex.add_resource("video")
        
        self.api_gw_base_url = api.url

        # extr-srv-api-delete-task-processor (invoked by extr-srv-api-delete-task)
        lambda_key = "extr-srv-api-delete-task-processor"
        lambda_extr_srv_api_delete_task_processor_role = self.create_role(lambda_key, ["s3","dynamodb","transcribe", "s3vectors"])
        lambda_extr_srv_api_delete_task_processor = self.create_lambda(
            lambda_key, 
            lambda_extr_srv_api_delete_task_processor_role, 
            {
                'TRANSCRIBE_JOB_PREFIX': TRANSCRIBE_JOB_PREFIX,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'S3_BUCKET_DATA': self.s3_bucket_name_extraction,
                'S3_VECTOR_BUCKET': S3_VECTOR_BUCKET_NAME,
                'S3_VECTOR_INDEX': S3_VECTOR_INDEX_NAME,
                'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE
            }, 
            timeout_s=120, memory_size=10240, ephemeral_storage_size=4096,
            layers=[self.moviepy_layer],
        )

        # POST v1/extraction/video/delete-task
        lambda_key="extr-srv-api-delete-task"
        lambda_srv_api_delete_task_role = self.create_role(lambda_key, ["lambda"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', 
            root=ex_video, path1="delete-task", method="POST", auth=self.cognito_authorizer, 
            role=lambda_srv_api_delete_task_role, 
            lambda_file_name=lambda_key, 
            memory_m=128, timeout_s=20, ephemeral_storage_size=512,
            evns={
                'LAMBDA_NAME_DELETE_PROCESS': f"{LAMBDA_NAME_PREFIX}extr-srv-api-delete-task-processor"#lambda_extr_srv_api_delete_task_processor.function_name,
            },
        )   

        # POST v1/extraction/video/get-clip-shots
        lambda_key="extr-srv-api-clip-get-shots"
        lambda_srv_api_clip_get_shots_role = self.create_role(lambda_key, ["s3","dynamodb"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', 
            root=ex_video, path1="get-clip-shots", method="POST", auth=self.cognito_authorizer, 
            role=lambda_srv_api_clip_get_shots_role, 
            lambda_file_name=lambda_key, 
            memory_m=1280, timeout_s=30, ephemeral_storage_size=512,
            evns={
                'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S': S3_PRESIGNED_URL_EXPIRY_S,
            },
        )   

        # POST /v1/extraction/video/get-task
        lambda_key='extr-srv-api-get-task'
        lambda_extr_srv_api_get_task_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="get-task", method="POST", auth=self.cognito_authorizer, 
                role=lambda_extr_srv_api_get_task_role, 
                lambda_file_name=lambda_key,
                memory_m=128, timeout_s=20, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S': S3_PRESIGNED_URL_EXPIRY_S,
            })        
        
        # POST /v1/extraction/get-task-frames
        lambda_key='extr-srv-api-frame-get-frames'
        lambda_es_get_task_frames_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="get-task-frames", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_get_task_frames_role, 
                lambda_file_name=lambda_key,
                memory_m=1024, timeout_s=30, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S':S3_PRESIGNED_URL_EXPIRY_S,
            })        
        
        # POST /v1/extraction/get-task-transcripts
        lambda_key='extr-srv-api-get-transcripts'
        lambda_extr_srv_api_get_task_transcripts_role = self.create_role(lambda_key, ["s3","dynamodb","bedrock"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="get-task-transcripts", method="POST", auth=self.cognito_authorizer, 
                role=lambda_extr_srv_api_get_task_transcripts_role, 
                lambda_file_name=lambda_key,
                memory_m=1280, timeout_s=30, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
            })    
        
        # POST /v1/extraction/video/manage-s3-presigned-url
        lambda_key='extr-srv-api-manage-s3-presigned-url'
        lambda_es_manage_s3_url_role = self.create_role(lambda_key, ["s3"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="manage-s3-presigned-url", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_manage_s3_url_role,
                lambda_file_name=lambda_key,
                memory_m=128, timeout_s=10, ephemeral_storage_size=512,
                evns={
                    'S3_PRESIGNED_URL_EXPIRY_S': S3_PRESIGNED_URL_EXPIRY_S,
                    'VIDEO_UPLOAD_S3_BUCKET': self.s3_bucket_name_extraction,
                    'VIDEO_UPLOAD_S3_PREFIX': VIDEO_UPLOAD_S3_PREFIX
                },
            )   
              
        # POST /v1/extraction/search-task
        lambda_key='extr-srv-api-search-tasks' 
        lambda_extr_srv_api_search_tasks_role = self.create_role(lambda_key, ["s3","dynamodb"])
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="search-task", method="POST", auth=self.cognito_authorizer, 
                role=lambda_extr_srv_api_search_tasks_role,
                lambda_file_name=lambda_key,
                memory_m=10240, timeout_s=30, ephemeral_storage_size=1024,
                evns={
                    'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                    'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                    'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                    'S3_PRESIGNED_URL_EXPIRY_S': S3_PRESIGNED_URL_EXPIRY_S,
                }
        )

        # POST /v1/extraction/search-vector
        lambda_key = "extr-srv-api-clip-search-vector"
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="search-vector", method="POST", auth=self.cognito_authorizer, 
                role=self.create_role(lambda_key, ["s3","dynamodb","bedrock","s3vectors"]),
                lambda_file_name=lambda_key,
                memory_m=10240, timeout_s=30, ephemeral_storage_size=1024,
                evns={
                    'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                    'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
                    'MODEL_ID': MODEL_ID_BEDROCK_MME,
                    'NOVA_S3_VECTOR_BUCKET': S3_VECTOR_BUCKET_NAME,
                    'NOVA_S3_VECTOR_INDEX': S3_VECTOR_INDEX_NAME,
                    'S3_BUCKET_DATA': self.s3_bucket_name_extraction,
                    'S3_PRE_SIGNED_URL_EXPIRY_S': S3_PRESIGNED_URL_EXPIRY_S
                }
        )

        # POST /v1/extraction/video/start-task
        lambda_key='extr-srv-api-start-task'
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="start-task", method="POST", auth=self.cognito_authorizer, 
                role=self.create_role(lambda_key, ["s3","dynamodb","states"]), 
                lambda_file_name=lambda_key,
                memory_m=128, timeout_s=30, ephemeral_storage_size=512,
                evns={
                    'STEP_FUNCTIONS_STATE_MACHINE_ARN_FRAME': self.sf_frame_based_flow.state_machine_arn,
                    'STEP_FUNCTIONS_STATE_MACHINE_ARN_CLIP': self.sf_clip_based_flow.state_machine_arn,
                    'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                },
            )
        
        # POST /v1/extraction/video/extr-srv-api-get-sm-url
        lambda_key = "extr-srv-api-get-sm-url"
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="get-sm-url", method="POST", auth=self.cognito_authorizer, 
                role=self.create_role(lambda_key, ["sagemaker"]), 
                lambda_file_name=lambda_key,
                memory_m=128, timeout_s=30, ephemeral_storage_size=512,
                evns={
                    'SM_NOTEBOOK_INSTANCE_NAME': f"{SM_NOTEBOOK_INSTANCE_NAME_PREFIX}analytics"
                },
            )

        # POST /v1/extraction/video/get-token-and-cost
        lambda_key = "extr-srv-api-get-token-and-cost"
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="get-token-and-cost", method="POST", auth=self.cognito_authorizer, 
                role=self.create_role(lambda_key, ["dynamodb"]), 
                lambda_file_name=lambda_key,
                memory_m=512, timeout_s=30, ephemeral_storage_size=512,
                evns={
                    'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE,
                },
            )

        # POST /v1/extraction/video/get-data-size
        lambda_key = "extr-srv-api-get-data-size"
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="get-data-size", method="POST", auth=self.cognito_authorizer, 
                role=self.create_role(lambda_key, ["s3", "dynamodb"]), 
                lambda_file_name=lambda_key,
                memory_m=512, timeout_s=60, ephemeral_storage_size=512,
                evns={
                    'S3_BUCKET': self.s3_bucket_name_extraction,
                    'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                    'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                    'DYNAMO_VIDEO_SHOT_TABLE': DYNAMO_VIDEO_SHOT_TABLE,
                    'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                    'DYNAMO_VIDEO_USAGE_TABLE': DYNAMO_VIDEO_USAGE_TABLE,
                },
            )

        # POST /v1/extraction/video/refresh-thumbnail-urls
        lambda_key = "extr-srv-api-refresh-thumbnail-urls"
        self.create_api_endpoint(id=f'{lambda_key}-ep', root=ex_video, path1="refresh-thumbnail-urls", method="POST", auth=self.cognito_authorizer, 
                role=self.create_role(lambda_key, ["s3"]), 
                lambda_file_name=lambda_key,
                memory_m=256, timeout_s=30, ephemeral_storage_size=512,
                evns={
                    'S3_PRESIGNED_URL_EXPIRY_S': S3_PRESIGNED_URL_EXPIRY_S,
                },
            )

        # API Gateway - end

    def create_role(self, function_name, policies):
        statements=[
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup"],
                resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
            ),
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/{LAMBDA_NAME_PREFIX}{function_name}:*"]
            )
        ]
        if "s3" in policies:
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    )
            )
        if "dynamodb" in policies:
            statements.append(
                _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem","dynamodb:DescribeTable","dynamodb:BatchWriteItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_SHOT_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_USAGE_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_SHOT_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_USAGE_TABLE}",
                        ]
                    ))
        if "bedrock" in policies:
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel","bedrock:GetAsyncInvoke"],
                        resources=[
                            "arn:aws:bedrock:*:*:foundation-model/*",
                            "arn:aws:bedrock:*:*:async-invoke/*",
                            "arn:aws:bedrock:*:*:inference-profile/*"
                        ]
                    )
            )
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["aws-marketplace:ViewSubscriptions","aws-marketplace:Subscribe"],
                        resources=[f"*"]
                    ),
            )
        if "states" in policies:
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["states:ListExecutions","states:StartExecution"],
                        resources=[f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:*"]
                    )
            )
        if "s3vectors" in policies:
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3vectors:*"],
                        resources=[f"arn:aws:s3vectors:{self.region}:{self.account_id}:bucket/{S3_VECTOR_BUCKET_NAME}*"]
                    )
            )
        if "lambda" in policies:
            statements.append(
                 _iam.PolicyStatement(
                    effect=_iam.Effect.ALLOW,
                    actions=["lambda:InvokeFunction"],
                    resources=[
                        f"arn:aws:lambda:{self.region}:{self.account_id}:function:{LAMBDA_NAME_PREFIX}extr-srv*"
                    ]
                ),
            )
        if "transcribe" in policies:
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["transcribe:StartTranscriptionJob", "transcribe:DeleteTranscriptionJob","transcribe:GetTranscriptionJob"],
                        resources=["*"]
                    ),
            )
        if "sagemaker" in policies:
            statements.append(
                _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sagemaker:DescribeNotebookInstance","sagemaker:CreatePresignedNotebookInstanceUrl"],
                        resources=[f"arn:aws:sagemaker:{self.region}:{self.account_id}:notebook-instance/*"]
                    ),
            )


        return _iam.Role(
            self, f"{function_name}-role",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={f"{function_name}-poliy": _iam.PolicyDocument(
            statements=statements
        )}
    )   

    def create_lambda(self, function_name, role, environment, timeout_s=30, memory_size=128, ephemeral_storage_size=512, layers=[]):
        return _lambda.Function(self, 
            id=f'{function_name}-lambda', 
            function_name=f'{LAMBDA_NAME_PREFIX}{function_name}', 
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler=f'{function_name}.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", f"extraction_service/lambda/{function_name}")),
            timeout=Duration.seconds(timeout_s),
            memory_size=memory_size,
            ephemeral_storage_size=Size.mebibytes(ephemeral_storage_size),
            role=role,
            environment=environment,
            layers=layers,
        )

    def create_api_endpoint(self, id, root, path1, method, auth, role, lambda_file_name, memory_m, timeout_s, ephemeral_storage_size, evns, layers=None):
        lambda_function = _lambda.Function(self, 
            id=f'{lambda_file_name}-lambda', 
            function_name=f'{LAMBDA_NAME_PREFIX}{lambda_file_name}', 
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler=f'{lambda_file_name}.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", f"extraction_service/lambda/{lambda_file_name}")),
            timeout=Duration.seconds(timeout_s),
            memory_size=memory_m,
            ephemeral_storage_size=Size.mebibytes(ephemeral_storage_size),
            role=role,
            environment=evns,
            layers=layers,
        )

        resource = root.add_resource(
                path1, 
                default_cors_preflight_options=_apigw.CorsOptions(
                allow_methods=['POST', 'OPTIONS'],
                allow_origins=_apigw.Cors.ALL_ORIGINS),
        )

        method = resource.add_method(
            method, 
            _apigw.LambdaIntegration(
                lambda_function,
                proxy=False,
                integration_responses=[
                    _apigw.IntegrationResponse(
                        status_code="200",
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                ]
            ),
            method_responses=[
                _apigw.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ],
            authorizer=auth,
            authorization_type=_apigw.AuthorizationType.COGNITO
        )