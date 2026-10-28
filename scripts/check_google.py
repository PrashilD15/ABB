"""Minimal credential/model diagnostic. Never prints credentials or request headers."""
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
load_dotenv('.env')
client = genai.Client(http_options=types.HttpOptions(timeout=20000))
try:
    response = client.models.generate_content(model=os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'), contents='Reply with the word OK.', config=types.GenerateContentConfig(max_output_tokens=32))
    print('Google generation succeeded:', bool(response.text))
except Exception as exc:
    print('Google generation failed:', type(exc).__name__, getattr(exc, 'code', ''))
    message = str(getattr(exc, 'message', 'No provider diagnostic')).replace(os.getenv('GOOGLE_API_KEY', 'not-configured'), '[REDACTED]')
    print(message[:1000])
