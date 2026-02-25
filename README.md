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
- PostgreSQL 14+ (with `pg_partman` extension)

## Setup

### 1. Clone the repository

```bash
cd sn-api-gateway
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

All chat-related endpoints require `Authorization: Bearer <jwt>` with a `user_id` claim.

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

### Analyze Phrase (Create or Continue a Chat)

```bash
POST /prompts/analyze
Content-Type: application/json
Authorization: Bearer <jwt>

{
  "text": "I am going to home.",
  "lang": "en"
}
```

**Response:**
```json
{
  "text": "I am going to home.",
  "lang": "en",
  "chat_id": "uuid",
  "issues": [
    {
      "text_part": "to home",
      "explanation": "The preposition 'to' is not used before 'home' in English"
    }
  ],
  "alternatives": [
    "I am going home."
  ],
  "assessment": "Minor preposition error common among non-native speakers"
}
```

### Send a Chat Message

```bash
POST /chats/{chat_id}/messages
Content-Type: application/json
Authorization: Bearer <jwt>

{
  "text": "Why is that wrong?"
}
```

### List Chat Messages (Cursor Pagination)

```bash
GET /chats/{chat_id}/messages?limit=50&cursor=...
Authorization: Bearer <jwt>
```

### Delete a Chat

```bash
DELETE /chats/{chat_id}
Authorization: Bearer <jwt>
```

### Readiness

```bash
GET /health/ready
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
- `CONFIG_DIR` (default: config/config.yaml): Path to YAML configuration
- `PROMPT_PATH` (default: config/prompt.txt): Prompt template path
- `EXAMPLES_PATH` (default: config/examples.yaml): Examples data path
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Database settings (used when not specified in YAML)

### YAML Configuration

The `config.yaml` file contains runtime settings, including:
- Logging level
- Model settings (name, temperature, max_tokens, concurrency, retries)
- Chat/message limits
- Database settings (optional)

Prompts and examples live in `config/prompt.txt` and `config/examples.yaml`.

## Development

### Project Structure

```
sn-api-gateway/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application and startup
│   ├── routers/         # API endpoints
│   ├── config.py        # Configuration management
│   ├── models.py        # Pydantic models
│   ├── schema.py        # Request/response schemas
│   └── services.py      # Business logic and LangChain integration
├── config/              # Language prompts and examples
├── pyproject.toml       # Python dependencies
├── Dockerfile          # Container configuration
├── .env.example        # Example environment variables
└── README.md
```

### Adding a New Language

1. Edit `config/examples.yaml` and update `config/prompt.txt` as needed
2. Restart the application
3. The new language will be automatically available

## License

See SPEC.md for project specifications.
