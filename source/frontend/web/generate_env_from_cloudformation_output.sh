#!/bin/bash
# Usage: ./generate_env.sh <STACK_NAME>
# Example: ./generate_env.sh MyAppStack

# Get stack outputs as JSON
OUTPUTS=$(aws cloudformation describe-stacks \
  --stack-name "BedrockMmRootStack" \
  --query "Stacks[0].Outputs" \
  --output json)

if [ -z "$OUTPUTS" ]; then
  echo "Error: Unable to fetch outputs for stack $STACK_NAME"
  exit 1
fi

# Helper function to extract output value by key
get_output() {
  echo "$OUTPUTS" | jq -r ".[] | select(.OutputKey==\"$1\") | .OutputValue"
}

# Extract values
COGNITO_REGION="us-east-1"
COGNITO_USER_POOL_ID=$(get_output "CognitoUserPoolId")
COGNITO_USER_POOL_CLIENT_ID=$(get_output "CognitoAppClientId")
COGNITO_IDENTITY_POOL_ID=$(get_output "CognitoIdentityPoolId")
APIGATEWAY_BASE_URL_NOVA_SRV=$(get_output "APIGatewayBaseURLNovaMMEService")
APIGATEWAY_BASE_URL_TLABS_SRV=$(get_output "APIGatewayBaseURLTLabsMMEService")
APIGATEWAY_BASE_URL_EXTR_SRV=$(get_output "APIGatewayBaseURLExtractionServiceframeandclipbaedworkflow")
AGENTCORE_RUNTIME_ARN=$(get_output "AgentCoreRuntimeArn")

# Generate .env file
cat <<EOF > .env
REACT_APP_COGNITO_REGION="${COGNITO_REGION}"
REACT_APP_COGNITO_USER_POOL_ID="${COGNITO_USER_POOL_ID}"
REACT_APP_COGNITO_USER_POOL_CLIENT_ID="${COGNITO_USER_POOL_CLIENT_ID}"
REACT_APP_APIGATEWAY_BASE_URL_NOVA_SRV="${APIGATEWAY_BASE_URL_NOVA_SRV}"
REACT_APP_APIGATEWAY_BASE_URL_TLABS_SRV="${APIGATEWAY_BASE_URL_TLABS_SRV}"
REACT_APP_APIGATEWAY_BASE_URL_EXTR_SRV="${APIGATEWAY_BASE_URL_EXTR_SRV}"
REACT_APP_COGNITO_IDENTITY_POOL_ID="${COGNITO_IDENTITY_POOL_ID}"
REACT_APP_AGENTCORE_RUNTIME_ARN="${AGENTCORE_RUNTIME_ARN}"
REACT_APP_AGENTCORE_RUNTIME_ENDPOINT_NAME="DEFAULT"
REACT_APP_READONLY_DISPLAY_MENUS="frame,clip,novamme,tlabsmme,agent"
REACT_APP_SHOW_SETTINGS_ICON="true"
EOF

echo ".env file generated successfully:"
cat .env
