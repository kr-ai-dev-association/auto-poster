import os
import asyncio
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_models():
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        print("Available models:")
        # client.models.list() returns an iterator or list
        # The SDK usage might vary, assuming standard list_models approach
        # For google-genai v1.0, it might be client.models.list()
        for m in client.models.list():
            print(f"- {m.name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models()
