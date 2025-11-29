'''
"Source": mm_embedding | text_embedding | text,
'''
import json
import boto3
import os
import utils
import re
from urllib.parse import urlparse

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")

S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 

s3 = boto3.client('s3')

def lambda_handler(event, context):
    search_text = event.get("SearchText", "")
    page_size = event.get("PageSize", 10)
    from_index = event.get("FromIndex", 0)
    request_by = event.get("RequestBy")
    source = event.get("Source")
    task_type = event.get("TaskType")
    
    if search_text is None:
        search_text = ""
    if len(search_text) > 0:
        search_text = search_text.strip()

    tasks = utils.scan_task_with_pagination(DYNAMO_VIDEO_TASK_TABLE, keyword=search_text, start_index=0, page_size=1000)
    result = []
    if tasks:
        for task in tasks:
            r = {
                    "TaskId": task["Id"],
                    "FileName": task["Request"]["FileName"],
                    "TaskName": task["Request"].get("TaskName"),
                    "Name": task["Request"].get("Name",task["Request"]["FileName"]),
                    "RequestTs": task["RequestTs"],
                    "Status": task["Status"],
                    "RequestBy": task.get("RequestBy")
                }
            if "MetaData" in task and "VideoMetaData" in task["MetaData"]:
                video_meta = task["MetaData"]["VideoMetaData"]
                if "ThumbnailS3Bucket" in video_meta:
                    r["S3Bucket"] = video_meta["ThumbnailS3Bucket"]
                    r["S3Key"] = video_meta["ThumbnailS3Key"]
                r["MetaData"] = {"VideoMetaData": {"Size": video_meta.get("Size", 0), "Duration": video_meta.get("Duration", 0)}}
            result.append(r)

    # Sort by RequestTs
    result = sorted(result, key=lambda x: x.get("RequestTs"), reverse=True)

    # Pagination
    end_index = from_index + page_size
    if end_index > len(result):
        end_index = len(result)

    result = result[from_index:end_index]

    # Generate URL
    for r in result:
        if "S3Bucket" in r and "S3Key" in r:
            r["ThumbnailUrl"] = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': r["S3Bucket"], 'Key': r["S3Key"]},
                    ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                )
            del r["S3Bucket"]
            del r["S3Key"]

    return {
        'statusCode': 200,
        'body': result
    }
