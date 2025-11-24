import json
import boto3
import os, time

COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
COGNITO_INVITATION_EMAIL_TEMPLATE = os.environ.get("COGNITO_INVITATION_EMAIL_TEMPLATE")
COGNITO_INVITATION_EMAIL_TITLE = os.environ.get("COGNITO_INVITATION_EMAIL_TITLE")
CLOUD_FRONT_URL = os.environ.get("CLOUD_FRONT_URL")
APP_NAME = os.environ.get("APP_NAME")

COGNITO_USER_EMAILS = os.environ.get("COGNITO_USER_EMAILS")
COGNITO_USER_NAME = os.environ.get("COGNITO_USER_NAME")
COGNITO_USER_PWD = os.environ.get("COGNITO_USER_PWD")


S3_BUCKET_NAME_STAGING = os.environ.get("S3_BUCKET_NAME_STAGING")
S3_BUCKET_NAME_WEB = os.environ.get("S3_BUCKET_NAME_WEB")

SM_NOTEBOOK_INSTANCE_NAME = os.environ.get("SM_NOTEBOOK_INSTANCE_NAME")

s3 = boto3.resource('s3')
s3_client = boto3.client('s3')
cloudfront = boto3.client('cloudfront')
cognito = boto3.client('cognito-idp')
sm = boto3.client("sagemaker")

def on_event(event, context):
  print(event)
  request_type = event['RequestType']
  if request_type == 'Create': return on_create(event)
  if request_type == 'Update': return on_update(event)
  if request_type == 'Delete': return on_delete(event)
  raise Exception("Invalid request type: %s" % request_type)

def on_create(event):
  # Update S3 data bucket CORS with CloudFront URL
  update_s3_cors(S3_BUCKET_NAME_STAGING, CLOUD_FRONT_URL)
  
  # Copy web build
  copy_s3_prefix_to_root(S3_BUCKET_NAME_STAGING, "build/", S3_BUCKET_NAME_WEB)

  # Update Cognitio Invitation Email template
  try:
    email_body = COGNITO_INVITATION_EMAIL_TEMPLATE.replace("##CLOUDFRONT_URL##", CLOUD_FRONT_URL) \
                  .replace("##APP_NAME##", APP_NAME) 
    email_title = COGNITO_INVITATION_EMAIL_TITLE.replace("##APP_NAME##", APP_NAME)
    response = cognito.update_user_pool(
        UserPoolId=COGNITO_USER_POOL_ID,
        AdminCreateUserConfig={
          'AllowAdminCreateUserOnly': True,
          'InviteMessageTemplate': {
              #'SMSMessage': 'string',
              'EmailMessage': email_body,
              'EmailSubject': email_title
          }
        }
    )
    print(response)
  except Exception as ex:
    print("Failed to update email template:", ex)

  # Add users to Cognito user pool
  if COGNITO_USER_EMAILS is not None and len(COGNITO_USER_EMAILS) > 0:
    for email in COGNITO_USER_EMAILS.split(','):
      try:
        cognito.admin_create_user(
          UserPoolId=COGNITO_USER_POOL_ID,
          Username=email,
          UserAttributes=[
            {
                'Name': 'email',
                'Value': email
            },
          ],
          DesiredDeliveryMediums=['EMAIL'],
        )
      except Exception as ex:
        print(ex)
    
  if COGNITO_USER_NAME and COGNITO_USER_PWD:
    try:
      # Create user without email flow
      cognito.admin_create_user(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=COGNITO_USER_NAME,
        UserAttributes=[],
        MessageAction='SUPPRESS'
      )
    except Exception as ex:
      print(ex)
    try:
      # Reset password
      cognito.admin_set_user_password(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=COGNITO_USER_NAME,
        Password=COGNITO_USER_PWD,
        Permanent=True # This makes the password permanent
      )

    except Exception as ex:
      print(ex)
    
  return True

def on_update(event):
  return

def on_delete(event):
  return { 'IsComplete': True }

def on_complete(event):
  return

def is_complete(event):
  return { 'IsComplete': True }

def update_s3_cors(bucket_name, cloudfront_url):
    """Update S3 bucket CORS to allow all origins for presigned URLs"""
    try:
        cors_config = {
            'CORSRules': [
                {
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'HEAD'],
                    'AllowedOrigins': ['*'],
                    'ExposeHeaders': ['ETag', 'x-amz-server-side-encryption', 'x-amz-request-id', 'x-amz-id-2'],
                    'MaxAgeSeconds': 3600
                },
                {
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['POST', 'PUT', 'DELETE'],
                    'AllowedOrigins': ['*'],
                    'ExposeHeaders': ['ETag'],
                    'MaxAgeSeconds': 3600
                }
            ]
        }
        s3_client.put_bucket_cors(Bucket=bucket_name, CORSConfiguration=cors_config)
        print(f"✅ Updated CORS for {bucket_name} to allow all origins")
    except Exception as ex:
        print(f"Failed to update CORS: {ex}")

def copy_s3_prefix_to_root(src_bucket_name, src_prefix, dest_bucket_name):
    src_bucket = s3.Bucket(src_bucket_name)
    dest_bucket = s3.Bucket(dest_bucket_name)

    for obj in src_bucket.objects.filter(Prefix=src_prefix):
        # Remove the prefix part from the key
        dest_key = obj.key[len(src_prefix):] if obj.key.startswith(src_prefix) else obj.key

        if dest_key == "":
            continue  # skip folder markers

        print(f"Copying {obj.key} → {dest_bucket_name}/{dest_key}")

        dest_bucket.copy(
            {
                'Bucket': src_bucket_name,
                'Key': obj.key
            },
            dest_key
        )