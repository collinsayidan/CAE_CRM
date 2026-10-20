"""WSGI entrypoint for hosting (gunicorn in the Docker image; Vercel): exposes a module-level `app`."""

from app import create_app

app = create_app()
