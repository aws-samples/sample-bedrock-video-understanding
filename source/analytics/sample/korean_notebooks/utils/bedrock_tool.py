import boto3
import json

# Create Bedrock client
bedrock = boto3.client('bedrock-runtime')


def bedrock_converse(model_id, prompt, local_file_path=None, tool_config=None, inference_config=None):
    """
    Call Amazon Bedrock Converse API with a prompt and optional local file (e.g., video).

    Args:
        model_id (str): The Bedrock model ID to use.
        prompt (str): Text prompt to provide to the model.
        local_file_path (str, optional): Path to a local file (e.g., MP4 video) to include as input. Defaults to None.
        tool_config (dict, optional): Tool configuration to pass to the Converse API. Defaults to None.
        inference_config (dict, optional): Inference parameters like maxTokens, temperature, etc.
                                           Defaults to {"maxTokens": 500, "topP": 0.1, "temperature": 0.3}.

    Returns:
        dict or None: The raw API response from Bedrock Converse, or None if an exception occurred.
    """
    if not inference_config:
        inference_config = {"maxTokens": 500, "topP": 0.1, "temperature": 0.3}

    input_content, input_format = None, None
    if local_file_path:
        input_format = local_file_path.split('.')[-1].lower()
        with open(local_file_path, "rb") as f:
            input_content = f.read()

    try:
        # Construct the message
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                ]
            }
        ]

        # Add video content if present
        if input_format in ["mp4"]:
            messages[0]["content"].append({
                "video": {
                    "format": input_format,
                    "source": {
                        "bytes": input_content
                    },
                }
            })

        # Call Bedrock Converse
        if tool_config:
            response = bedrock.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig=inference_config,
                toolConfig=tool_config
            )
        else:
            response = bedrock.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig=inference_config,
            )

        # Check for successful API response
        if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise Exception(f"API request failed: {response['ResponseMetadata']['HTTPStatusCode']}")

        return response

    except Exception as ex:
        print(f"Bedrock API error: {ex}")
        return None


def remove_quotes(content):
    """
    Remove leading and trailing single or double quotes from a string.

    Args:
        content (str): The string to clean.

    Returns:
        str: String without surrounding quotes.
    """
    if content and ((content.startswith('"') and content.endswith('"')) or
                    (content.startswith("'") and content.endswith("'"))):
        return content[1:-1]
    return content


def parse_converse_response(response):
    """
    Parse the response from Bedrock Converse to extract tool usage or text output.

    Args:
        response (dict): The raw response returned from Bedrock Converse API.

    Returns:
        str or None: Extracted tool usage or text result as a JSON string with quotes removed.
                     Returns None if response is empty or unparseable.
    """
    if not response:
        return None

    tool_use, txt_result = None, None
    contents = response.get("output", {}).get("message", {}).get("content", [])

    for c in contents:
        if "toolUse" in c:
            tool_use = c["toolUse"].get("input")
        elif "text" in c:
            txt_result = c["text"]

    if tool_use:
        return remove_quotes(json.dumps(tool_use, ensure_ascii=False))
    elif txt_result:
        return remove_quotes(json.dumps(txt_result, ensure_ascii=False))
    elif "content" in response:
        return remove_quotes(json.dumps(response["content"], ensure_ascii=False))
    return remove_quotes(json.dumps(response, ensure_ascii=False))
