'''
1. Read Transcribe transcription and subtitle from s3
2. Update DB
3. Start extraction step functions workflow
'''
import json
import boto3
import os
import utils
import re
from datetime import datetime, timezone

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
TLABS_S3_VECTOR_BUCKET = os.environ.get("TLABS_S3_VECTOR_BUCKET")
TLABS_S3_VECTOR_INDEX = os.environ.get("TLABS_S3_VECTOR_INDEX")
TLABS_S3_VECTOR_INDEX_30 = os.environ.get("TLABS_S3_VECTOR_INDEX_30")
DYNAMO_VIDEO_USAGE_TABLE = os.environ.get("DYNAMO_VIDEO_USAGE_TABLE")

s3 = boto3.client('s3')
s3vectors = boto3.client('s3vectors') 

def lambda_handler(event, context):
    if event is None or "detail" not in event:
        return {
            'statusCode': 400,
            'body': 'Invalid trigger'
        }
    s3_bucket, s3_key, task_id = None, None, None
    try:
        s3_bucket = event["detail"]["bucket"]["name"]
        s3_key = event["detail"]["object"]["key"]
        task_id = s3_key.split('/')[1]
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': f'Error parsing S3 trigger: {ex}'
        }

    
    # Ignore key path contains /search/ trigger - they are managed differently by the search process
    if '/tlabs/search/' in s3_key:
        return {
            'statusCode': 400,
            'body': 'Search trigger. Ignored.'
        }

    
    if not s3_bucket or not s3_key or not task_id:
        return {
            'statusCode': 400,
            'body': 'Invalid trigger'
        }

    # Get embedding result from S3
    obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    content = obj['Body'].read().decode('utf-8')
    output = json.loads(content).get("data")

    # Add embeddings to S3 Vector: batch size 100
    embeddings, batch_size, counter = [], 200, 0
    for o in output:
        index_name = TLABS_S3_VECTOR_INDEX
        embed = {
                "key": f'{task_id}_{o["embeddingOption"]}_{o["startSec"]}_{o["endSec"]}',
                "data": {"float32": o["embedding"]},
                "metadata": {
                    "task_id": task_id, 
                    "embeddingOption": o["embeddingOption"], 
                    "startSec": o["startSec"], 
                    "endSec": o["endSec"]
                }
            }
        
        if "embeddingScope" in o:
            # Marengo 3.0 embedding
            index_name = TLABS_S3_VECTOR_INDEX_30
            embed["metadata"]["embeddingScope"] = o["embeddingScope"]

        embeddings.append(embed)
        
        counter += 1
        if len(embeddings) >= batch_size or counter >= len(output):
            # Write embeddings into vector index with metadata.
            try:
                s3vectors.put_vectors(
                    vectorBucketName=TLABS_S3_VECTOR_BUCKET,   
                    indexName=index_name,   
                    vectors=embeddings
                )
            except Exception as vec_err:
                # Ignore duplicate key errors - vectors already exist
                if "duplicate" not in str(vec_err).lower():
                    raise vec_err
                print(f"Vectors already exist, skipping: {vec_err}")
            embeddings = []

    # Update DynamoDB task status
    doc = None
    try:
        doc = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, id=task_id)
        if doc is not None:
            # Update video task status
            doc["Status"] = "completed"
            doc["Id"] = task_id
            doc["EmbedCompleteTs"] = datetime.now(timezone.utc).isoformat()
        
            # update DB: video_task
            utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, doc)

            # store usage
            model_id = doc.get("Request",{}).get("ModelId")
            duration_s = doc.get("MetaData",{}).get("VideoMetaData", {}).get("Duration", 0)
            update_usage_to_db(task_id, model_id, duration_s)
    except Exception as ex:
        print('Doc does not exist',ex)
    

    return {
        'statusCode': 200,
        'body': 'Task completed.'
    }

def update_usage_to_db(task_id, model_id, duration_s):
    usage = {
        "id": f"{task_id}_talbs_mme",
        "index": None,
        "type": "tlabs_mme_video",
        "name": "TwelveLabs Marengo video embedding",
        "task_id": task_id,
        "model_id": model_id,
        "duration_s": duration_s
    }
    utils.dynamodb_table_upsert(DYNAMO_VIDEO_USAGE_TABLE, usage)    
    return usage