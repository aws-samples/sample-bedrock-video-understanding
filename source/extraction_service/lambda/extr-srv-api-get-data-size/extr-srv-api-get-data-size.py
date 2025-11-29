import json
import boto3
import os
import utils

S3_BUCKET = os.environ.get("S3_BUCKET")
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_SHOT_TABLE = os.environ.get("DYNAMO_VIDEO_SHOT_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_TRANS_TABLE")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Nova and TwelveLabs tables (derived from naming convention)
DYNAMO_NOVA_TASK_TABLE = "bedrock_mm_nova_video_task"
DYNAMO_TLABS_TASK_TABLE = "bedrock_mm_tlabs_video_task"

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    task_id = event.get("task_id") or event.get("TaskId")
    workflow_type = event.get("workflow_type", "frame_based")  # frame_based, shot_based, nova_mme, tlabs
    
    if not task_id:
        return {'statusCode': 400, 'body': {'error': 'Missing task_id parameter.'}}
    
    if not S3_BUCKET:
        return {'statusCode': 500, 'body': {'error': 'S3 bucket configuration missing.'}}
    
    try:
        data_breakdown = {}
        total_size = 0
        total_files = 0
        
        # Define S3 prefixes and DynamoDB tables based on workflow type
        if workflow_type == "frame_based":
            s3_prefixes = {
                'video_frame': f'tasks/{task_id}/video_frame_/',
                'frame_outputs': f'tasks/{task_id}/frame_outputs/',
                'transcribe': f'tasks/{task_id}/transcribe/',
            }
            dynamo_tables = {
                'task_metadata': DYNAMO_VIDEO_TASK_TABLE,
                'frame_analysis': DYNAMO_VIDEO_FRAME_TABLE,
                'transcription': DYNAMO_VIDEO_TRANS_TABLE,
            }
            vector_config = None
            
        elif workflow_type == "shot_based":
            s3_prefixes = {
                'shot_clip': f'tasks/{task_id}/shot_clip/',
                'shot_outputs': f'tasks/{task_id}/shot_outputs/',
                'shot_vector': f'tasks/{task_id}/shot_vector/',
                'transcribe': f'tasks/{task_id}/transcribe/',
            }
            dynamo_tables = {
                'task_metadata': DYNAMO_VIDEO_TASK_TABLE,
                'shot_analysis': DYNAMO_VIDEO_SHOT_TABLE,
                'transcription': DYNAMO_VIDEO_TRANS_TABLE,
            }
            # Shot based uses shot_vector S3 prefix for embeddings
            vector_config = {'prefix_key': 'shot_vector', 'dimension': 1024}
            
        elif workflow_type == "nova_mme":
            s3_prefixes = {
                'nova_mme': f'tasks/{task_id}/nova-mme/',
            }
            dynamo_tables = {
                'task_metadata': DYNAMO_NOVA_TASK_TABLE,
            }
            vector_config = {'prefix_key': 'nova_mme', 'dimension': 1024}
            
        elif workflow_type == "tlabs":
            s3_prefixes = {
                'tlabs': f'tasks/{task_id}/tlabs/',
            }
            dynamo_tables = {
                'task_metadata': DYNAMO_TLABS_TASK_TABLE,
            }
            vector_config = {'prefix_key': 'tlabs', 'dimension': 1024}
            
        else:
            return {'statusCode': 400, 'body': {'error': f'Unknown workflow_type: {workflow_type}'}}
        
        # Calculate S3 data sizes
        for data_type, prefix in s3_prefixes.items():
            try:
                size_info = utils.calculate_s3_prefix_size(S3_BUCKET, prefix)
                if size_info['file_count'] > 0:
                    data_breakdown[data_type] = size_info
                    total_size += size_info['size']
                    total_files += size_info['file_count']
            except Exception as e:
                print(f"Error calculating S3 size for {data_type}: {str(e)}")
        
        # Calculate DynamoDB data sizes
        for data_type, table_name in dynamo_tables.items():
            if not table_name:
                continue
            try:
                print(f"Querying DynamoDB table: {table_name} for task_id: {task_id}")
                size_info = utils.calculate_dynamodb_task_size(table_name, task_id)
                print(f"DynamoDB result for {table_name}: {size_info}")
                if size_info['record_count'] > 0:
                    data_breakdown[f'dynamodb_{data_type}'] = {
                        'size': size_info['estimated_size'],
                        'file_count': size_info['record_count'],
                        'max_file_size': size_info['max_record_size']
                    }
                    total_size += size_info['estimated_size']
                    total_files += size_info['record_count']
            except Exception as e:
                print(f"Error calculating DynamoDB size for {data_type}: {str(e)}")
        
        # Estimate S3 Vectors size from embedding files
        if vector_config and vector_config['prefix_key'] in s3_prefixes:
            try:
                prefix = s3_prefixes[vector_config['prefix_key']]
                vector_size = estimate_vectors_from_s3(S3_BUCKET, prefix, vector_config['dimension'])
                if vector_size['estimated_size'] > 0:
                    data_breakdown['s3_vectors'] = vector_size
                    total_size += vector_size['estimated_size']
                    total_files += vector_size['vector_count']
            except Exception as e:
                print(f"Error estimating S3 Vectors: {str(e)}")
        
        return {
            'statusCode': 200,
            'body': {
                'task_id': task_id,
                'workflow_type': workflow_type,
                'total_size': total_size,
                'total_files': total_files,
                'data_breakdown': data_breakdown,
                'bucket': S3_BUCKET,
                'region': AWS_REGION
            }
        }
        
    except Exception as e:
        print(f"Error calculating data sizes: {str(e)}")
        return {'statusCode': 500, 'body': {'error': f'Error calculating data sizes: {str(e)}'}}


def estimate_vectors_from_s3(bucket, prefix, dimension):
    """
    Estimate S3 Vectors storage size by counting vectors in embedding files.
    Nova MME: embedding-*.jsonl files contain one vector per line
    TwelveLabs: output.json contains data array with embeddings
    Shot Based: shot_vector/*.json files
    """
    try:
        paginator = s3.get_paginator('list_objects_v2')
        vector_count = 0
        
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith('.jsonl'):
                    # Nova MME: count lines in JSONL file
                    response = s3.get_object(Bucket=bucket, Key=key)
                    content = response['Body'].read().decode('utf-8')
                    vector_count += len([l for l in content.strip().split('\n') if l])
                elif key.endswith('output.json'):
                    # TwelveLabs: count items in data array
                    response = s3.get_object(Bucket=bucket, Key=key)
                    content = json.loads(response['Body'].read().decode('utf-8'))
                    vector_count += len(content.get('data', []))
                elif key.endswith('.json') and 'shot_vector' in prefix:
                    # Shot Based: each JSON file is one vector
                    vector_count += 1
        
        # Each vector: dimension * 4 bytes (float32) + ~100 bytes metadata
        size_per_vector = (dimension * 4) + 100
        estimated_size = vector_count * size_per_vector
        
        return {
            'vector_count': vector_count,
            'estimated_size': estimated_size,
            'size_per_vector': size_per_vector
        }
        
    except Exception as e:
        print(f"Error estimating vectors from S3: {str(e)}")
        return {'vector_count': 0, 'estimated_size': 0, 'size_per_vector': 0}
