# AnyoneAI Interviewer Backend

Backend API for a proof-of-concept AI interview platform. Built with FastAPI + SQLAlchemy and containerized with Docker.

## Features
- Roles and question bank
- Candidate creation
- Interview creation (predefined role or custom role with generated questions)
- Answer submission with automatic scoring (stub)
- Interview transcript + evaluation retrieval

## Tech Stack
- FastAPI
- SQLAlchemy (SQLite by default)
- Docker + docker-compose

## Quick Start (Local)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env.example | xargs)
uvicorn app.main:app --reload
```

Open API docs:
- http://localhost:8000/docs

## Quick Start (Docker)
```bash
docker compose up --build
```

## Environment Variables
- `DATABASE_URL` (default: `sqlite:///./app.db`)
- `DEFAULT_QUESTION_COUNT` (default: `5`)
- `AUTH_ENABLED` (default: `true`)
- `AUTH_HEADER` (default: `X-API-Key`)
- `API_KEYS` (format: `key1:admin,key2:recruiter,key3:interviewer`)
- `USER_CREDENTIALS` (format: `user1:pass1:admin,user2:pass2:recruiter`)
- `JWT_SECRET` (default: `dev_secret_change_me`)
- `JWT_ALGORITHM` (default: `HS256`)
- `JWT_ACCESS_MINUTES` (default: `30`)
- `JWT_REFRESH_DAYS` (default: `7`)

## Auth + RBAC
All endpoints (except `/health`, `/docs`, `/redoc`, `/openapi.json`) require an API key header.
JWT auth is also supported via `Authorization: Bearer <token>`.

Built-in roles:
- `admin` can access everything.
- `recruiter` can manage candidates and interviews.
- `interviewer` can run interview sessions and submit answers.

Example:
```bash
curl -H "X-API-Key: your_key_here" http://localhost:8000/interviews
```

## API Overview
- `POST /roles`
- `GET /roles`
- `POST /questions`
- `GET /questions`
- `POST /candidates`
- `GET /candidates`
- `POST /interviews`
- `GET /interviews`
- `GET /interviews/{interview_id}`
- `GET /interviews/{interview_id}/transcript`
- `POST /interviews/{interview_id}/start`
- `GET /interviews/{interview_id}/next-question`
- `POST /interviews/{interview_id}/submit-answer`
- `POST /interviews/{interview_id}/end`
- `POST /interviews/{interview_id}/answers`
- `POST /interviews/{interview_id}/finish`
- `POST /admin/interviews`
- `GET /admin/interviews`
- `GET /admin/interviews/{interview_id}`
- `PATCH /admin/interviews/{interview_id}`
- `DELETE /admin/interviews/{interview_id}`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/signup`

## Example Flow
```bash
# Create role
curl -X POST http://localhost:8000/roles \
  -H "Content-Type: application/json" \
  -d '{"name":"ML Engineer","description":"Machine Learning Engineer"}'

# Add a question
curl -X POST http://localhost:8000/questions \
  -H "Content-Type: application/json" \
  -d '{"role_id":1,"text":"Explain bias-variance tradeoff.","category":"technical"}'

# Create candidate
curl -X POST http://localhost:8000/candidates \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Ana","last_name":"Lopez","email":"ana@example.com"}'

# Start interview with predefined role
curl -X POST http://localhost:8000/interviews \
  -H "Content-Type: application/json" \
  -d '{"candidate_id":1,"role_id":1}'
```

## Notes
- Question generation and evaluation are stubbed in:
  - `app/services/question_generation.py`
  - `app/services/evaluation.py`
  Replace with LLM integrations when ready.
- SQLite is used for fast iteration. Swap to Postgres by updating `DATABASE_URL`.
- Database schema lives in `app/models.py` and is created on startup.
