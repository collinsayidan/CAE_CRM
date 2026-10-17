"""WSGI entrypoint for hosting (Vercel, gunicorn): exposes a module-level `app`."""

from app import create_app

app = create_app()
