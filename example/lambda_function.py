from google import genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY is None:
    raise ValueError(
        "GEMINI_API_KEY is not set in your environment variables.")

client = genai.Client(api_key=GEMINI_API_KEY)


def lambda_handler(event, context):
    """
    AWS Lambda function to handle incoming requests and generate responses using Gemini API.
    """
    input_text = event.get('input_text', 'Hello, how can I help you?')

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=input_text
    )

    return {
        'statusCode': 200,
        'body': response.text
    }
