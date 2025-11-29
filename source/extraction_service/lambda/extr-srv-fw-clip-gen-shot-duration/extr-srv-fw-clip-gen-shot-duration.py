import json
import boto3
import os
import base64
import utils
from scenedetect import detect, ContentDetector
import numbers,decimal
from boto3.dynamodb.conditions import Key

'''
layer:
[
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
]
'''
DYNAMO_VIDEO_SHOT_TABLE = os.environ.get("DYNAMO_VIDEO_SHOT_TABLE")
SHOT_GROUP_SIZE = 10

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

video_analysis_table = dynamodb.Table(DYNAMO_VIDEO_SHOT_TABLE)

local_path = '/tmp/'

def lambda_handler(event, context):
    if event is None or "Request" not in event:
        return 'Invalid request'
    
    task_id = event["Request"].get("TaskId")
    s3_bucket, s3_key = None, None
    start_sec, length_sec, use_fixed_length_sec, min_clip_sec = None, None, None, None
    video_duration = None
    try:
        s3_bucket = event["Request"]["Video"]["S3Object"]["Bucket"]
        s3_key = event["Request"]["Video"]["S3Object"]["Key"]

        if "PreProcessSetting" in event["Request"]:
            if event["Request"]["PreProcessSetting"].get("StartSec"):
                start_sec = float(event["Request"]["PreProcessSetting"]["StartSec"])
            if event["Request"]["PreProcessSetting"].get("LengthSec"):
                length_sec = float(event["Request"]["PreProcessSetting"]["LengthSec"])
            if event["Request"]["PreProcessSetting"].get("UseFixedLengthSec"):
                use_fixed_length_sec = float(event["Request"]["PreProcessSetting"]["UseFixedLengthSec"])
            if event["Request"]["PreProcessSetting"].get("MinClipSec"):
                min_clip_sec = float(event["Request"]["PreProcessSetting"]["MinClipSec"])
            video_duration = float(event["MetaData"]["VideoMetaData"]["Duration"])
    except Exception as ex:
        print(ex)
        return 'Invalid Request'

    # Download video to local disk
    local_file_path = local_path + s3_key.split('/')[-1]
    s3.download_file(s3_bucket, s3_key, local_file_path)
    print(f"{s3_bucket}{s3_key}")
    
    # Generate shots
    shots = []
    if use_fixed_length_sec:
        # Fixed interval shots
        shots = split_video_fixed_length(
            video_duration,
            use_fixed_length_sec=use_fixed_length_sec,
        )
    else:
        # Use OpenCV scene detection
        shots = segment_video_opencv(local_file_path, video_duration)
        
        # If scene detection returns no shots, treat entire video as single shot
        if not shots and video_duration:
            print(f"Scene detection found no shots, treating entire video ({video_duration}s) as single shot")
            shots = [{
                "index": 1,
                "start_time": 0.0,
                "end_time": video_duration,
                "duration": video_duration,
            }]

    if start_sec or length_sec or min_clip_sec:
        print("!!!!",start_sec, length_sec, min_clip_sec)
        shots = apply_clip_params(shots, start_sec, length_sec, min_clip_sec)

    # Store shots to database
    for shot in shots:
        shot_db = {
            "id": f'{task_id}_shot_{shot["index"]}',
            "task_id":task_id,
            "index": shot["index"],
            "start_time": shot["start_time"],
            "end_time": shot["end_time"],
            "duration": shot["duration"],
            "analysis_type": 'shot'
        }
        resposne = video_analysis_table.put_item(Item=convert_to_dynamo_format(shot_db))

    # Group the shots into multiple items for parallel processing in the next step.
    groups = []
    for i in range(0, len(shots), SHOT_GROUP_SIZE):
        group = shots[i:i+SHOT_GROUP_SIZE]
        groups.append({
            "shots": group,
            "task_id": task_id,
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
        })

    event["shot_groups"] = groups
    event["s3_bucket_clip_output"] = s3_bucket
    event["s3_prefix_clip_output"] = f'tasks/{task_id}/shot_clip/'
    
    return event

def segment_video_opencv(local_file_path, video_duration):
    # Use OpenCV
    segments = []
    scene_list = detect(local_file_path, ContentDetector())
    for i, (start_time, end_time) in enumerate(scene_list):
        start_seconds = start_time.get_seconds()
 
        end_seconds = end_time.get_seconds()
        if video_duration and end_seconds >= video_duration:
            end_seconds = video_duration
        duration_seconds = end_seconds - start_seconds

        idx = i + 1
        shot = {
            "index": idx,
            "start_time": start_seconds,
            "end_time": end_seconds,
            "duration": duration_seconds,
        }
        segments.append(shot)

    return segments


def split_video_fixed_length(total_duration, use_fixed_length_sec):
    segments = []
    index = 0
    start_time = 0.0

    while start_time < total_duration:
        end_time = min(start_time + use_fixed_length_sec, total_duration)
        duration = end_time - start_time
        segments.append({
            "index": index,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration
        })
        index += 1
        start_time = end_time

    return segments

def apply_clip_params(segments, start_sec=None, length_sec=None, min_clip_sec=None):
    # --- Step 1: Apply start_sec and length_sec ---
    filtered = []
    for seg in segments:
        if start_sec is not None and seg["end_time"] <= start_sec:
            continue  # segment ends before start_sec
        if length_sec is not None and seg["start_time"] >= start_sec + length_sec:
            continue  # segment starts after allowed window

        # Trim if partial overlap
        new_start = max(seg["start_time"], start_sec if start_sec else seg["start_time"])
        new_end = min(seg["end_time"], (start_sec + length_sec) if length_sec else seg["end_time"])
        duration = new_end - new_start
        if duration > 0:
            filtered.append({
                "index": seg["index"],
                "start_time": new_start,
                "end_time": new_end,
                "duration": duration
            })

    # --- Step 2: Merge small clips if min_clip_sec is set ---
    if min_clip_sec:
        merged = []
        buffer = None

        for seg in filtered:
            if buffer is None:
                buffer = seg
            else:
                if buffer["duration"] < min_clip_sec:
                    # merge with current
                    buffer["end_time"] = seg["end_time"]
                    buffer["duration"] = buffer["end_time"] - buffer["start_time"]
                else:
                    merged.append(buffer)
                    buffer = seg
        if buffer:
            merged.append(buffer)

        filtered = merged

    # --- Step 3: Reindex ---
    for i, seg in enumerate(filtered):
        seg["index"] = i

    return filtered

def convert_to_dynamo_format(item):
    """
    Recursively convert an object to a DynamoDB item format.
    """
    if isinstance(item, dict):
        return {k: convert_to_dynamo_format(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_dynamo_format(v) for v in item]
    elif isinstance(item, float):
        return decimal.Decimal(str(item))
    #elif isinstance(item, decimal.Decimal):
    #    return float(item)
    else:
        return item