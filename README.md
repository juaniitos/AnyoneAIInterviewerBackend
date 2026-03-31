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

## Auth Quickstart
You can authenticate in **one of two ways**:

1) **API Key** (header-based)
2) **JWT Bearer Token** (issued via `/auth/login`)

### API Key (header)
API keys are defined in the `API_KEYS` env var. Example:
```
API_KEYS=dev_admin_key:admin,dev_recruiter_key:recruiter,dev_interviewer_key:interviewer
```
Use one of these keys:
```bash
curl -H "X-API-Key: dev_admin_key" http://localhost:8000/roles
```

### JWT (login + refresh)
JWT login uses `USER_CREDENTIALS` and expects **email + password**.
Example credentials:
```
USER_CREDENTIALS=admin:adminpass:admin,recruiter:recruitpass:recruiter,interviewer:intpass:interviewer
```

Login:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin","password":"adminpass"}'
```

Use the access token:
```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/interviews
```

Refresh:
```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

### Sign up (Admin users)
`/auth/signup` creates an **AdminUser** with a hashed password.
By default it is **public** (no API key required).

Signup:
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"admin2@example.com","password":"securepass","name":"Admin Two"}'
```

If you want to **require an API key** for signup, remove `/auth/signup` from the public paths in:
`app/security/auth.py`

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
All endpoints (except `/health`, `/docs`, `/redoc`, `/openapi.json`, `/auth/login`, `/auth/refresh`, `/auth/signup`) require auth.
You can authenticate in **either** of these ways:

1) **API Key** (header-based)
2) **JWT Bearer Token** (issued via `/auth/login`)

Built-in roles:
- `admin` can access everything.
- `recruiter` can manage candidates and interviews.
- `interviewer` can run interview sessions and submit answers.

### API Key auth
API keys are defined in the `API_KEYS` env var. Example:
```
API_KEYS=dev_admin_key:admin,dev_recruiter_key:recruiter,dev_interviewer_key:interviewer
```
Pick **one key** from that list and send it as a header:
```bash
curl -H "X-API-Key: dev_admin_key" http://localhost:8000/roles
```

### JWT auth (login + refresh)
Login uses the `USER_CREDENTIALS` env var and expects **email + password**:
```
USER_CREDENTIALS=admin:adminpass:admin,recruiter:recruitpass:recruiter,interviewer:intpass:interviewer
```

Login:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin","password":"adminpass"}'
```

Use the access token:
```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/interviews
```

Refresh:
```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

### Sign up (Admin users)
`/auth/signup` is public (no API key required). It creates an **AdminUser** with a hashed password:
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"admin2@example.com","password":"securepass","name":"Admin Two"}'
```

If you are still being asked for an API key on `/auth/signup`, redeploy the latest code or make sure `AUTH_ENABLED` is `true` and the service has the updated public path list.

## API Overview
- `POST /roles`
- `GET /roles`
- `POST /questions`
- `GET /questions`
- `POST /candidates`
- `GET /candidates`
- `POST /templates`
- `GET /templates`
- `GET /templates/{template_id}`
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
# Create job role
curl -X POST http://localhost:8000/roles \
  -H "Content-Type: application/json" \
  -d '{"name":"ML Engineer","description":"Machine Learning Engineer","seniority":"mid","department":"AI"}'

# Add a question
curl -X POST http://localhost:8000/questions \
  -H "Content-Type: application/json" \
  -d '{"job_role_id":"ROLE_UUID","text":"Explain bias-variance tradeoff.","category":"technical","difficulty":"medium"}'

# Create template
curl -X POST http://localhost:8000/templates \
  -H "Content-Type: application/json" \
  -d '{"job_role_id":"ROLE_UUID","name":"Default","question_count":5,"system_prompt":"..."}'

# Create candidate
curl -X POST http://localhost:8000/candidates \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Ana Lopez","email":"ana@example.com"}'

# Start interview session
curl -X POST http://localhost:8000/interviews \
  -H "Content-Type: application/json" \
  -d '{"candidate_id":"CANDIDATE_UUID","job_role_id":"ROLE_UUID","template_id":"TEMPLATE_UUID"}'
```

## Notes
- Question generation and evaluation are stubbed in:
  - `app/services/question_generation.py`
  - `app/services/evaluation.py`
  Replace with LLM integrations when ready.
- SQLite is used for fast iteration. Swap to Postgres by updating `DATABASE_URL`.
- Database schema lives in `app/models.py` and is created on startup.
