#!/bin/bash

# Quick frontend update script - use this when you only changed frontend code
# This is much faster than full CDK deployment

if [ -z "$CDK_DEFAULT_REGION" ]; then
    read -p "Enter your target AWS region (e.g., us-east-1): " CDK_DEFAULT_REGION
    export CDK_DEFAULT_REGION
fi

REGION="$CDK_DEFAULT_REGION"

echo "🚀 Quick Frontend Update (Region: $REGION)"
echo "========================"

# Get CodeBuild project name
PROJECT_NAME=$(aws codebuild list-projects --region $REGION --query 'projects[?contains(@, `bedrockmmfrontendappbuild`)]' --output text | head -1)

if [ -z "$PROJECT_NAME" ]; then
    echo "❌ CodeBuild project not found. Run deploy-cloudshell.sh first."
    exit 1
fi

# Get project details to find source bucket
SOURCE_LOCATION=$(aws codebuild batch-get-projects --region $REGION --names "$PROJECT_NAME" --query 'projects[0].source.location' --output text)
BUCKET=$(echo $SOURCE_LOCATION | cut -d'/' -f1)
KEY=$(echo $SOURCE_LOCATION | cut -d'/' -f2-)

echo "📦 Packaging frontend source code..."
cd ../source/frontend/web
zip -rq /tmp/frontend-source.zip . -x "node_modules/*" "build/*" ".git/*" "*.log"
cd ../../../deployment

echo "⬆️  Uploading to S3..."
aws s3 cp /tmp/frontend-source.zip s3://$SOURCE_LOCATION
rm /tmp/frontend-source.zip

echo "🔨 Starting CodeBuild..."
BUILD_ID=$(aws codebuild start-build --region $REGION --project-name "$PROJECT_NAME" --query 'build.id' --output text)

if [ -z "$BUILD_ID" ]; then
    echo "❌ Failed to start build"
    exit 1
fi

echo "⏳ Waiting for build to complete..."
while true; do
    STATUS=$(aws codebuild batch-get-builds --region $REGION --ids "$BUILD_ID" --query 'builds[0].buildStatus' --output text)
    
    if [ "$STATUS" = "SUCCEEDED" ]; then
        echo "✅ Build completed successfully!"
        
        # Copy artifacts from staging bucket to web bucket
        echo "📤 Deploying to web bucket..."
        STAGING_BUCKET=$(echo $BUCKET | sed 's/cdk-hnb659fds-assets/bedrock-mm/')
        WEB_BUCKET="bedrock-mm-web-108362357227-$REGION"
        
        aws s3 sync s3://$STAGING_BUCKET/build/ s3://$WEB_BUCKET/ --delete --region $REGION
        echo "✅ Deployed to S3"
        break
    elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "FAULT" ] || [ "$STATUS" = "STOPPED" ]; then
        echo "❌ Build failed: $STATUS"
        exit 1
    else
        echo "   Status: $STATUS"
        sleep 10
    fi
done

echo "🔄 Invalidating CloudFront cache..."
WEBSITE_URL=$(aws cloudformation describe-stacks --stack-name BedrockMmRootStack --region $REGION --query 'Stacks[0].Outputs[?contains(OutputKey, `Website`)].OutputValue' --output text 2>/dev/null)
CF_DOMAIN=$(echo $WEBSITE_URL | sed 's|https://||' | sed 's|/.*||')
DISTRIBUTION_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?contains(DomainName, '$CF_DOMAIN')].Id" --output text | head -1)

if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
    aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" > /dev/null 2>&1
    echo "✅ Done! Changes will be visible in 1-2 minutes."
    echo "🌐 Website: $WEBSITE_URL"
    echo "💡 Hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R)"
else
    echo "⚠️  Could not invalidate cache. Manual invalidation may be needed."
fi
