#!/bin/sh
set -eu

if [ "${AUTO_CREATE_TABLES:-true}" = "false" ]; then
  echo "[backend] running alembic migrations"
  alembic upgrade head
fi

echo "[backend] starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
