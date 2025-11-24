import json
import boto3
import os

S3_PRESIGNED_URL_EXPIRY_S = int(os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600))

s3 = boto3.client('s3')

def lambda_handler(event, context):
    body = json.loads(event.get('body', '{}')) if isinstance(event.get('body'), str) else event
    thumbnails = body.get('Thumbnails', [])
    
    result = []
    for thumb in thumbnails:
        bucket = thumb.get('S3Bucket')
        key = thumb.get('S3Key')
        
        if bucket and key:
            try:
                url = s3.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': bucket,
                        'Key': key,
                        'ResponseCacheControl': 'no-cache'
                    },
                    ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                )
                result.append({
                    'S3Bucket': bucket,
                    'S3Key': key,
                    'ThumbnailUrl': url
                })
            except Exception as e:
                result.append({
                    'S3Bucket': bucket,
                    'S3Key': key,
                    'Error': str(e)
                })
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }
