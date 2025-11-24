#!/bin/bash

set -e

# Check if running from deployment directory
if [ ! -f "app.py" ] || [ ! -f "requirements.txt" ]; then
    echo "Error: This script must be run from the deployment directory."
    echo "Please cd to the deployment directory and run: bash ./deploy.sh"
    exit 1
fi

# Check and prompt for required environment variables
if [ -z "$CDK_DEFAULT_ACCOUNT" ]; then
    read -p "Enter your AWS Account ID: " CDK_DEFAULT_ACCOUNT
    export CDK_DEFAULT_ACCOUNT
fi

if [ -z "$CDK_DEFAULT_REGION" ]; then
    read -p "Enter your target AWS region (e.g., us-east-1): " CDK_DEFAULT_REGION
    export CDK_DEFAULT_REGION
fi

if [ -z "$CDK_INPUT_USER_EMAILS" ]; then
    read -p "Enter email address(es) for login (comma-separated): " CDK_INPUT_USER_EMAILS
    export CDK_INPUT_USER_EMAILS
fi

# Install Node CDK package
sudo npm install aws-cdk

# Build frontend first to avoid node_modules symlink issues
# Note: This initial build creates a basic version without proper env vars
# The CDK FrontendStack will rebuild it with correct environment variables
echo "Building React frontend (initial build)..."
cd ../source/frontend/web
npm install --silent
npm run build --silent
cd ../../../deployment

# Create or reuse Python Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies only if requirements changed or venv is new
if [ ! -f ".venv/.requirements_installed" ] || [ "requirements.txt" -nt ".venv/.requirements_installed" ]; then
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
    touch .venv/.requirements_installed
else
    echo "Python dependencies already up to date."
fi

# Bootstrap CDK - this step will launch a CloudFormation stack to provision the CDK package, which will take ~2 minutes.
cdk bootstrap aws://${CDK_DEFAULT_ACCOUNT}/${CDK_DEFAULT_REGION}
export AWS_DEFAULT_REGION=${CDK_DEFAULT_REGION}

echo "Deploying CDK stack with parameters:"
echo "  User Emails: ${CDK_INPUT_USER_EMAILS}"
echo "  User Name: ${CDK_INPUT_USER_NAME}"

# Force CDK to recognize source code changes by clearing cache
echo "Clearing CDK cache to ensure latest source code is used..."
rm -rf cdk.out/

# Deploy CDK package - this step will launch one CloudFormation stack with three nested stacks for different sub-systems.
# The FrontendStack will use CodeBuild to rebuild the React app with proper environment variables
cdk deploy --parameters inputUserEmails=${CDK_INPUT_USER_EMAILS} --parameters inputUserName=${CDK_INPUT_USER_NAME} --requires-approval never --all

echo "Deployment completed successfully!"
echo "The frontend has been rebuilt with proper environment variables via CodeBuild."

# Deploy frontend artifacts to web bucket
echo "Deploying frontend to web bucket..."
export CDK_DEFAULT_REGION=${CDK_DEFAULT_REGION}
bash ./update-frontend.sh