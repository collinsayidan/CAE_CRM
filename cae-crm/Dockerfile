# CAE CRM for Docker hosts such as Coolify. The app listens on port 8000 behind the host's HTTPS proxy.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CAE_HOSTED=1 \
    CAE_ENV=production

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Run as an ordinary user, not root.
RUN useradd --create-home --uid 10001 cae && mkdir -p /app/instance && chown -R cae /app
USER cae

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

# Two worker processes with four threads each suits a small server; raise CAE_WORKERS on a bigger one.
CMD ["sh", "-c", "exec gunicorn wsgi:app --bind 0.0.0.0:8000 --workers ${CAE_WORKERS:-2} --threads 4 --timeout 120 --graceful-timeout 30 --access-logfile -"]
