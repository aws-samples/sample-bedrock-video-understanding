'''
Call Bedrock Converse API for image understanding
Get sutitles match frame timestamp
Sync frame to DB
'''
import json
import boto3
import os
import utils
import base64
from io import BytesIO
import re
import time

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_TRANS_TABLE")

LOCAL_PATH = '/tmp/'

s3 = boto3.client('s3')
bedrock = boto3.client('bedrock-runtime') 

def lambda_handler(event, context):
    if event is None or "Request" not in event or "Key" not in event:
        return {
            "Error": "Invalid Request"
        }
    task_id = event["Request"].get("TaskId")
    setting = event["Request"].get("ExtractionSetting",{}).get("Vision",{}).get("Frame")
    s3_bucket = event["MetaData"]["VideoFrameS3"]["S3Bucket"]
    s3_prefix = event["MetaData"]["VideoFrameS3"]["S3Prefix"]
    s3_key = event.get("Key")
    file_name = event["Request"].get("FileName", "")

    enabled = setting.get("Enabled")
    if enabled == False:
        # Ignore frame analysis
        return event

    if task_id is None or setting is None or s3_bucket is None or s3_key is None or not s3_key.endswith('.png'):
        return {
            "Error": "Invalid Request"
        }

    frame_id = s3_key.split('/')[-1].replace('.png','')
    ts = float(frame_id.split("_")[-1])

    frame = utils.get_frame_by_id(DYNAMO_VIDEO_FRAME_TABLE, f'{task_id}_{ts}', task_id)
    if frame is None:
        frame = {
            "id": f'{task_id}_{ts}',
            "timestamp": ts,
            "task_id": task_id,
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
        }

    # Prompts - Bedrock
    promptConfigs = setting.get("PromptConfigs")
    if promptConfigs:
        frame["frame_outputs"] = []
        for config in promptConfigs:
            response = bedrock_converse(config=config, image_s3_bucket=s3_bucket, image_s3_key=s3_key)
            custom_output = parse_converse_response(response)
            print(custom_output)
            frame["frame_outputs"].append({
                "name": config["name"], 
                "model_id": config["modelId"],
                "value": custom_output
            })

        # Store to S3
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/frame_outputs/output_{ts}.json', Body=json.dumps(frame["frame_outputs"]))

    # Update database: video_frame
    utils.dynamodb_table_upsert(DYNAMO_VIDEO_FRAME_TABLE, frame)

    # include frame into event object
    event["frame"] = frame

    return event

def parse_converse_response(response):
    if not response:
        return None

    tool_use, txt_result = None, None
    contents = response.get("output",{}).get("message",{}).get("content",[])
    for c in contents:
        if "toolUse" in c:
            tool_use = c["toolUse"].get("input")
        elif "text" in c:
            txt_result = c["text"]
    
    if tool_use:
        return json.dumps(tool_use)
    elif txt_result:
        return json.dumps(txt_result)
    elif "content" in response:
        return json.dumps(response["content"])
    return json.dumps(response)

def bedrock_converse(config, max_retries=3, retry_delay=1, image_s3_bucket=None, image_s3_key=None):
    inference_config = config.get("inferConfig")
    if not inference_config:
        inference_config = {"maxTokens": 500, "topP": 0.1, "temperature": 0.3}
    if "modelId" in config and "anthropic" in config["modelId"]:
        del inference_config["topP"]

    retries = 0
    while retries < max_retries:
        try:
            # Construct the message with text and image content
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": config["prompt"]
                        },
                    ]
                }
            ]

            if image_s3_bucket and image_s3_key:
                file_obj = s3.get_object(Bucket=image_s3_bucket, Key=image_s3_key)
                image_content = file_obj['Body'].read()
                messages[0]["content"].append({
                            "image": {
                                "format": "png",
                                "source": {
                                    "bytes": image_content
                                },
                            }
                        })

            # Call Bedrock Converse
            if config.get("toolConfig"):
                response = bedrock.converse(
                    modelId=config["modelId"],
                    messages=messages,
                    inferenceConfig=inference_config,
                    toolConfig=config["toolConfig"]
                )
            else:
                response = bedrock.converse(
                    modelId=config["modelId"],
                    messages=messages,
                    inferenceConfig=inference_config,
                )
            #print(parse_converse_response(response))
            if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
                raise Exception(f"API request failed: {response["ResponseMetadata"]['HTTPStatusCode']}")

            return response
        except Exception as ex:
            print(ex)
            retries += 1
            time.sleep(retry_delay)

    return None