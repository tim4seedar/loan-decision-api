import os
import openai
from dotenv import load_dotenv

load_dotenv() # Loads variables from your .env file

openai.api_key = os.getenv("OPENAI_API_KEY")

def call_gpt(prompt: str) -> str:
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=300,
    )
    return response.choices[0].text.strip()