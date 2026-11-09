# CampusBite backend image (Docker / D7 / D23).
#
# Secrets policy: this image must never be *built* with secret material —
# there are no build args and no COPY of .env (see .dockerignore). Real
# values enter at *runtime* via environment injection (compose `environment`
# + `--env-file`). The app refuses to start on a placeholder JWT_SECRET (D4).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source (.dockerignore keeps .env, .venv, data/, tests out).
COPY . .

# Never run as root.
# /data must exist and be owned by appuser: a *first-use* named volume is
# initialized from the image's directory ownership, and an empty root-owned
# /data makes SQLite fail with SQLITE_CANTOPEN when the non-root app runs.
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /data && chown appuser:appuser /data
USER appuser

EXPOSE 8000

# Documented single-worker setup (D1/D6): one uvicorn worker, one process.
# (uvicorn --workers N with SQLite + the startup-migration contract is not a
# supported configuration; see README.)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
