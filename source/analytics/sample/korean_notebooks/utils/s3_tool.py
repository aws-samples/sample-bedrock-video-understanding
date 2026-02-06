# Get video task metadata from DynamoDB / S3
import boto3
import json
import re

S3_BUCKET_NAME_TEMPLATE_DATA = 'bedrock-mm-{account_id}-{region}'
S3_KEY_TEMPLATE_TRANSCRIPT_VTT = "tasks/{task_id}/transcribe/{task_id}_transcribe.vtt"
S3_KEY_TEMPLATE_TRANSCRIPT = "tasks/{task_id}/transcribe/{task_id}_transcribe.json"
S3_KEY_TEMPLATE_SHOT_CLIP = "tasks/{task_id}/shot_clip/"
S3_KEY_TEMPLATE_SHOT_OUTPUT = "tasks/{task_id}/shot_outputs/"
S3_KEY_TEMPLATE_SHOT_VECTOR = "tasks/{task_id}/shot_vector/"
S3_KEY_TEMPLATE_UPLOAD = "tasks/{task_id}/upload/"
S3_KEY_TEMPLATE_FRAME_IMAGE = "tasks/{task_id}/video_frame_/"
S3_KEY_TEMPLATE_FRAME_OUTPUT = "tasks/{task_id}/frame_outputs/"

FRAME_OUTPUT_FILE_NAME_TEMPLATE = "output_{timestamp}.json"
SHOT_OUTPUT_FILE_NAME_TEMPLATE = "output_{index}_{start_time}_{end_time}.json"

s3 = boto3.resource('s3')
session = boto3.session.Session()
sts = session.client("sts")
account_id = sts.get_caller_identity()["Account"]
region = session.region_name
S3_BUCKET_NAME = S3_BUCKET_NAME_TEMPLATE_DATA.format(account_id=account_id, region=region)


def get_transcripts(task_id, s3_bucket=S3_BUCKET_NAME):
    """
    Retrieve video transcription subtitles from S3 VTT file.

    Args:
        task_id (str): The ID of the video processing task.
        s3_bucket (str): S3 bucket name. Defaults to the current account/region bucket.

    Returns:
        list[dict]: List of subtitle blocks with start and end timestamps in milliseconds 
                    and transcription text. Each dict has keys: 'start_ts', 'end_ts', 'transcription'.
    """
    s3_key = S3_KEY_TEMPLATE_TRANSCRIPT_VTT.format(task_id=task_id)

    subtitles = []
    try:
        s3_clientobj = s3.Object(s3_bucket, s3_key)
        s3_clientdata = s3_clientobj.get()["Body"].read().decode("utf-8")
    
        
        blocks = re.split(r'\n{2,}', s3_clientdata.strip())
        for block in blocks:
            lines = block.split('\n')
            if len(lines) <= 1:
                continue
    
            index = int(lines[0]) if lines[0].isdigit() else None
            timecodes = re.findall(r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})', lines[1])
            text = '\n'.join(lines[2:]).strip() if len(lines) > 2 else None
    
            if index is not None and timecodes and text is not None:
                start_ts, end_ts = timecodes[0]
                subtitles.append({
                    "start_ts": convert_timestamp_to_ms(start_ts),
                    "end_ts": convert_timestamp_to_ms(end_ts),
                    "transcription": text
                })
    except Exception as ex:
        print("No audio transcription")

    return subtitles

def convert_timestamp_to_ms(timestamp):
    try:
        # Split the timestamp into hours, minutes, seconds, and milliseconds
        hours, minutes, seconds_ms = timestamp.split(':')
        seconds, milliseconds = seconds_ms.split('.')
        
        # Convert to float and format the result
        result = float(hours) * 3600 + float(minutes) * 60 + float(seconds) + float(f"0.{milliseconds}")
        
        return round(result, 2)  # Round to 2 decimal places
    except ValueError as e:
        print(f"Error converting timestamp: {e}")
        return None


def get_all_s3_files(s3_bucket, prefix):
    """
    List all S3 objects under a given prefix and return as a list of dicts.

    Args:
        s3_bucket (str): The S3 bucket name.
        prefix (str): The S3 key prefix to list objects.

    Returns:
        list[dict]: Each dict contains 's3_bucket' and 's3_key' of an object.
    """
    file_list = []
    paginator = s3.meta.client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=s3_bucket, Prefix=prefix)

    for page in page_iterator:
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith('/'):
                    continue
                file_list.append({"s3_bucket": s3_bucket, "s3_key": key})

    return file_list


def get_shot_clips(task_id, s3_bucket=S3_BUCKET_NAME):
    """
    Get all shot clip files for a given task from S3.

    Args:
        task_id (str): The task ID.
        s3_bucket (str): S3 bucket name.

    Returns:
        list[dict]: List of S3 objects for shot clips.
    """
    s3_prefix = S3_KEY_TEMPLATE_SHOT_CLIP.format(task_id=task_id)
    return get_all_s3_files(s3_bucket, s3_prefix)


def get_frame_images(task_id, s3_bucket=S3_BUCKET_NAME):
    """
    Get all extracted video frame images for a task from S3.

    Args:
        task_id (str): Task ID.
        s3_bucket (str): S3 bucket name.

    Returns:
        list[dict]: List of S3 objects for frame images.
    """
    s3_prefix = S3_KEY_TEMPLATE_FRAME_IMAGE.format(task_id=task_id)
    return get_all_s3_files(s3_bucket, s3_prefix)


def get_uploaded_video(task_id, s3_bucket=S3_BUCKET_NAME):
    """
    Retrieve the S3 key of the uploaded video for a task. Returns the first video file found.

    Args:
        task_id (str): Task ID.
        s3_bucket (str): S3 bucket name.

    Returns:
        str: S3 key of the video file.

    Raises:
        FileNotFoundError: If no video file is found.
    """
    s3_prefix = S3_KEY_TEMPLATE_UPLOAD.format(task_id=task_id)
    response = s3.meta.client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_prefix)

    if 'Contents' in response:
        for obj in response['Contents']:
            key = obj['Key']
            if key.endswith('/'):
                continue
            if key.lower().endswith(('.mp4', '.mov', '.mkv', '.avi', '.flv', '.webm')):
                return key
            return key  # fallback to first file

    raise FileNotFoundError(f"No video file found in s3://{s3_bucket}/{s3_prefix}")


def get_shot_outputs(task_id, s3_bucket=S3_BUCKET_NAME, output_names=None):
    """
    Load all shot-level outputs (JSON files) for a task from S3 and optionally filter by output names.

    Args:
        task_id (str): Task ID.
        s3_bucket (str): S3 bucket name.
        output_names (list[str], optional): List of output names to filter. Defaults to None (all outputs).

    Returns:
        list[dict]: List of shot outputs with metadata ('index', 'start_time', 'end_time') added.
    """
    shots = []
    shot_output_prefix = S3_KEY_TEMPLATE_SHOT_OUTPUT.format(task_id=task_id)
    files = get_all_s3_files(s3_bucket, shot_output_prefix)

    for file in files:
        key = file.get("s3_key")
        if key.endswith(".json"):
            file_name = key.split("/")[-1]
            arr = file_name.split("_")
            index = arr[1]
            start_time = arr[2]
            end_time = arr[3]

            response = s3.Object(s3_bucket, key).get()
            content = response['Body'].read().decode('utf-8')

            try:
                data = json.loads(content)
                if data:
                    for output in data:
                        if output_names is None or output.get("name") in output_names:
                            output["index"] = index
                            output["start_time"] = start_time
                            output["end_time"] = end_time
                            shots.append(output)
            except json.JSONDecodeError:
                print(f"Skipping non-JSON file: {key}")

    return shots


def get_frame_outputs(task_id, s3_bucket=S3_BUCKET_NAME, output_names=None):
    """
    Load all frame-level outputs (JSON files) for a task from S3 and optionally filter by output names.

    Args:
        task_id (str): Task ID.
        s3_bucket (str): S3 bucket name.
        output_names (list[str], optional): List of output names to filter. Defaults to None (all outputs).

    Returns:
        list[dict]: List of frame outputs with 'timestamp' metadata added.
    """
    frames = []
    frame_output_prefix = S3_KEY_TEMPLATE_FRAME_OUTPUT.format(task_id=task_id)
    files = get_all_s3_files(s3_bucket, frame_output_prefix)

    for file in files:
        key = file.get("s3_key")
        if key.endswith(".json"):
            file_name = key.split("/")[-1]
            arr = file_name.split("_")
            timestamp = arr[1]

            response = s3.Object(s3_bucket, key).get()
            content = response['Body'].read().decode('utf-8')

            try:
                data = json.loads(content)
                if data:
                    for output in data:
                        if output_names is None or output.get("name") in output_names:
                            output["timestamp"] = timestamp
                            frames.append(output)
            except json.JSONDecodeError:
                print(f"Skipping non-JSON file: {key}")

    return frames
