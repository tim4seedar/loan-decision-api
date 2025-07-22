import os
import openai
from dotenv import load_dotenv

load_dotenv()  # Loads variables from your .env file

openai.api_key = os.getenv("OPENAI_API_KEY")


def call_gpt(
    prompt: str,
    model: str = "gpt-3.5-turbo",
    max_tokens: int = 300,
    temperature: float = 0.7,
) -> str:
    """Send a prompt to the OpenAI Chat API and return the response text."""

    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # ChatCompletion responses include the assistant message under 'message'
    return response.choices[0].message["content"].strip()
