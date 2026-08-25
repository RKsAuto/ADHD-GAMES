# Container image for free hosts that build from a Dockerfile — Hugging Face
# Spaces, Koyeb, Google Cloud Run, Fly.io, a Raspberry Pi, etc.
#
# Hugging Face Spaces (free, no credit card) expects the app on port 7860,
# which is the default below; PORT overrides it on hosts that inject one.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Written at runtime when MONGO_URI is unset; harmless when it is set.
RUN mkdir -p /app/data && chmod 777 /app/data

ENV PORT=7860 \
    SELF_PING_MINUTES=0
EXPOSE 7860

# 4 workers so a whole class registering at once is served in parallel; the
# work per request is tiny (static files and small JSON writes), and the
# cross-process file lock keeps concurrent saves safe.
CMD ["sh", "-c", "exec gunicorn --workers 4 --timeout 60 --bind 0.0.0.0:${PORT} server:app"]
