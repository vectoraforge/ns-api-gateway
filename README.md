# SpeakNative API Gateway

API Gateway for linguistic analysis of phrases to identify non-native patterns and suggest natural alternatives.

## Features

- **Linguistic Analysis**: Analyze phrases to identify grammar, word choice, and phrasing issues
- **Multi-language Support**: Currently supports English (en) and Spanish (es)
- **Natural Alternatives**: Get multiple corrected versions with naturalness scores
- **Example Phrases**: Access example phrases with common non-native mistakes

## Requirements

- Python 3.12+
- OpenAI API key

## Setup

### 1. Clone the repository

```bash
cd api-gateway
```

### 2. Install dependencies

```bash
uv sync
```

For test dependencies:

```bash
uv sync --group test
```

### 4. Configure environment

Copy the example environment file and update with your values:

```bash
cp .env.example .env
```

Edit `.env` and set your OpenAI API key:

```
OPENAI_API_KEY=your_actual_api_key_here
```

### 5. Run the application

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Endpoints

### Get Examples

```bash
GET /prompts/examples?lang=en
```

**Response:**
```json
{
  "lang": "en",
  "examples": [
    "I am going to home.",
    "He do not like it.",
    ...
  ]
}
```

### Analyze Phrase

```bash
POST /prompts/analyze
Content-Type: application/json

{
  "phrase": "I am going to home.",
  "lang": "en"
}
```

**Response:**
```json
{
  "phrase": "I am going to home.",
  "lang": "en",
  "issues": [
    {
      "type": "preposition error",
      "phrase_part": "to home",
      "explanation": "The preposition 'to' is not used before 'home' in English"
    }
  ],
  "alternatives": [
    {
      "corrected": "I am going home.",
      "explanation": "Removed unnecessary preposition 'to'",
      "naturalness_score": 10.0
    }
  ],
  "overall_assessment": "Minor preposition error common among non-native speakers"
}
```

## Docker

### Build

```bash
docker build -t sn-api-gateway .
```

### Run

```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your_api_key \
  sn-api-gateway
```

## Configuration

### Environment Variables

- `OPENAI_API_KEY` (required): Your OpenAI API key
- `LLM_MODEL` (default: gpt-4o-mini): LLM model to use
- `LLM_TEMPERATURE` (default: 0.3): Temperature for LLM responses
- `LLM_MAX_TOKENS` (default: 1000): Maximum tokens for responses
- `LOG_LEVEL` (default: INFO): Logging level
- `CONFIG_DIR` (default: config/config.yaml): Path to YAML configuration

### YAML Configuration

The `config.yaml` file contains:
- Prompt templates for each language
- Example phrases for each language

Add new languages by extending the `prompts` and `examples` sections.

## Development

### Project Structure

```
api-gateway/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application and startup
│   ├── api.py           # API endpoints
│   ├── config.py        # Configuration management
│   ├── models.py        # Pydantic models
│   └── services.py      # Business logic and LangChain integration
├── config/              # Language prompts and examples
├── pyproject.toml       # Python dependencies
├── Dockerfile          # Container configuration
├── .env.example        # Example environment variables
└── README.md
```

### Adding a New Language

1. Edit `config.yaml` and add entries under `prompts` and `examples`
2. Restart the application
3. The new language will be automatically available

## License

See SPEC.md for project specifications.
