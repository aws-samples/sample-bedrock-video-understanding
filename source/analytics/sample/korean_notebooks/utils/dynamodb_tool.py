import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal
import json

# DynamoDB table names
DYNAMO_TABLE_TASK = 'bedrock_mm_extr_srv_video_task'
DYNAMO_TABLE_TRANSCRIPT = 'bedrock_mm_extr_srv_video_transcript'
DYNAMO_TABLE_FRAME = 'bedrock_mm_extr_srv_video_frame'
DYNAMO_VIDEO_SHOT_TABLE = 'bedrock_mm_extr_srv_video_shot'

# Create DynamoDB resource once
dynamodb = boto3.resource('dynamodb')


def convert_decimals(obj):
    """
    Recursively convert DynamoDB Decimal objects to int or float.

    Args:
        obj (dict, list, Decimal, or other): The object to convert.

    Returns:
        Converted object where all Decimals are replaced by int (if no fractional part) or float.
    """
    if isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    else:
        return obj


def get_transcripts(task_id, dynamodb_table=DYNAMO_TABLE_TRANSCRIPT):
    """
    Retrieve all transcripts for a given video task from DynamoDB with pagination.

    Args:
        task_id (str): The ID of the video task.
        dynamodb_table (str): DynamoDB table name containing transcript items.

    Returns:
        list[dict]: List of transcript items sorted by start timestamp.
                    Each item has 'start_ts', 'end_ts', 'transcription', etc., 
                    with 'task_id' and 'id' removed.
    """
    table = dynamodb.Table(dynamodb_table)
    transcripts = []
    last_evaluated_key = None

    while True:
        query_params = {
            "IndexName": "task_id-start_ts-index",
            "KeyConditionExpression": Key('task_id').eq(task_id),
            "ScanIndexForward": True
        }
        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_params)
        items = convert_decimals(response.get('Items', []))

        for item in items:
            item.pop("task_id", None)
            item.pop("id", None)
            transcripts.append(item)

        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break

    return transcripts


def get_shot_outputs(task_id, dynamodb_table=DYNAMO_VIDEO_SHOT_TABLE, output_names=None):
    """
    Retrieve all shot-level outputs for a given video task from DynamoDB with pagination.

    Args:
        task_id (str): The ID of the video task.
        dynamodb_table (str): DynamoDB table name containing shot-level outputs.
        output_names (list[str], optional): Filter outputs by name. Defaults to None (all outputs).

    Returns:
        list[dict]: List of shots. Each shot contains:
                    - 'start_time' (float)
                    - 'end_time' (float)
                    - 'outputs': list of dicts with 'name' and 'summary'.
    """
    table = dynamodb.Table(dynamodb_table)
    shots = []
    last_evaluated_key = None

    while True:
        query_params = {
            "IndexName": "task_id-index-index",  # Keep original index name
            "KeyConditionExpression": Key('task_id').eq(task_id),
            "ScanIndexForward": True
        }
        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_params)
        items = convert_decimals(response.get("Items", []))

        for item in items:
            outputs = item.get("outputs", [])
            if outputs:
                shot = {
                    "start_time": float(item.get("start_time", 0.0)),
                    "end_time": float(item.get("end_time", 0.0)),
                    "outputs": []
                }
                for output in outputs:
                    if output_names is None or output.get("name") in output_names:
                        shot["outputs"].append({
                            "name": output.get("name"),
                            "summary": output.get("value")
                        })
                shots.append(shot)

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return shots


def get_frame_outputs(task_id, dynamodb_table=DYNAMO_TABLE_FRAME, output_names=None):
    """
    Retrieve all frame-level outputs for a given video task from DynamoDB with pagination.

    Args:
        task_id (str): The ID of the video task.
        dynamodb_table (str): DynamoDB table name containing frame-level outputs.
        output_names (list[str], optional): Filter outputs by name. Defaults to None (all outputs).

    Returns:
        list[dict]: List of frames. Each frame contains:
                    - 'timestamp' (float)
                    - 'outputs': list of dicts with 'name' and 'summary'.
    """
    table = dynamodb.Table(dynamodb_table)
    frames = []
    last_evaluated_key = None

    while True:
        query_params = {
            "IndexName": "task_id-timestamp-index",
            "KeyConditionExpression": Key('task_id').eq(task_id),
            "ScanIndexForward": True
        }
        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.query(**query_params)
        items = convert_decimals(response.get("Items", []))

        for item in items:
            outputs = item.get("frame_outputs", [])
            if outputs:
                frame = {
                    "timestamp": float(item.get("timestamp", 0.0)),
                    "outputs": []
                }
                for output in outputs:
                    if output_names is None or output.get("name") in output_names:
                        frame["outputs"].append({
                            "name": output.get("name"),
                            "summary": output.get("value")
                        })
                frames.append(frame)

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return frames


def get_task(task_id, dynamodb_table=DYNAMO_TABLE_TASK):
    """
    Retrieve a single task by its ID from DynamoDB.

    Args:
        task_id (str): The ID of the task to retrieve.
        dynamodb_table (str): DynamoDB table name containing task items.

    Returns:
        dict or None: The task item with Decimals converted to int/float, or None if not found.
    """
    table = dynamodb.Table(dynamodb_table)
    
    try:
        response = table.get_item(Key={'Id': task_id})
        item = response.get('Item')
        
        if item:
            return convert_decimals(item)
        return None
    except Exception as e:
        print(f"Error retrieving task {task_id}: {e}")
        return None

def get_tasks_by_type(task_type=None, dynamodb_table='bedrock_mm_extr_srv_video_task'):
    """
    Retrieve all tasks with a specific TaskType from DynamoDB with pagination.

    Args:
        task_type (str, optional): The TaskType to filter by (e.g., 'clip', 'frame').
                                   If None, returns all tasks. Defaults to None.
        dynamodb_table (str): DynamoDB table name containing task items.

    Returns:
        list[dict]: List of task items with Decimals converted to int/float.
    """
    table = dynamodb.Table(dynamodb_table)
    tasks = []
    last_evaluated_key = None

    while True:
        scan_params = {}
        
        # Only add FilterExpression if task_type is provided
        if last_evaluated_key:
            scan_params["ExclusiveStartKey"] = last_evaluated_key

        response = table.scan(**scan_params)
        items = convert_decimals(response.get('Items', []))
        for item in items:
            if item.get("Request",{}).get("TaskType") == task_type:
                tasks.append(item)

        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break

    return tasks
