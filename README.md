# loan-decision-api

A FastAPI service for evaluating SME loan applications and generating underwriter narratives.

## Setup

### Requirements
- Python 3.10+
- Dependencies listed in `requirements.txt`

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment variables
The application expects a few variables to be defined. They can be exported in your shell or placed in a `.env` file (loaded automatically by `python-dotenv`).

```
OPENAI_API_KEY=your-openai-key
GPT_MODEL=gpt-3.5-turbo  # optional, overrides the default model
STAGING=True              # optional, enables staging behaviour
```

`OPENAI_API_KEY` is required for the GPT functionality. `GPT_MODEL` allows switching the model used by the OpenAI API. `STAGING` controls whether the `/underwriter-schema` endpoint returns the full schema or a production placeholder.

## Running the API

Start the application locally using Uvicorn:

```bash
uvicorn main:app --reload
```

Interactive documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Example requests

Evaluate SME risk:
```bash
curl -X POST http://localhost:8000/evaluate/sme-risk \
  -H 'Content-Type: application/json' \
  -d '{
        "smeProfile": "EB",
        "riskProfile": "T1",
        "stressedDSCR": 1.35,
        "loanAmount": 100000,
        "loanType": "secured",
        "industrySector": "Wholesale and Retail Trade",
        "providedDocs": []
      }'
```

Generate a narrative from an evaluation decision:
```bash
curl -X POST http://localhost:8000/generate-narrative \
  -H 'Content-Type: application/json' \
  -d '{
        "decision": "PROGRESS",
        "confidence": 0.87,
        "explanation": "EB/T1 with DSCR >125% qualifies for an unsecured loan."
      }'
```

## OpenAI integration

`gpt_client.py` handles the interaction with the OpenAI API:
```python
openai.api_key = os.getenv("OPENAI_API_KEY")

def call_gpt(
    prompt: str,
    model: str = "gpt-3.5-turbo",
    max_tokens: int = 300,
    temperature: float = 0.7,
) -> str:
    response = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message["content"].strip()
```
Keep your `OPENAI_API_KEY` secret and avoid committing it to version control. Validate any sensitive information before sending it to the API and use HTTPS in production.


