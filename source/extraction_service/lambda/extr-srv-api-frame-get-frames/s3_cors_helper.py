import boto3
from botocore.config import Config

def get_s3_client_with_cors():
    """
    Create S3 client configured to work with CORS.
    Uses signature version v4 which is required for CORS to work properly.
    """
    config = Config(
        signature_version='s3v4',
        s3={'addressing_style': 'virtual'}
    )
    return boto3.client('s3', config=config)

def generate_cors_friendly_presigned_url(bucket, key, expiration=3600):
    """
    Generate presigned URL that works with CORS by using proper signature version.
    """
    s3_client = get_s3_client_with_cors()
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )
