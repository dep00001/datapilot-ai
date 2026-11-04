from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models import init_db
from app.api import auth_router, dataset_router, feedback_router

# Initialize DB tables at startup
init_db()

app = FastAPI(
    title='DataPilot AI API',
    version='1.0.0',
    description=(
        'Secure AI-assisted data analytics API. '
        'Dataset files are stored privately per user. '
        'AI providers receive only minimized aggregate context.'
    ),
    docs_url='/docs',
    redoc_url='/redoc',
)

# CORS — only allow configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(',') if o.strip()],
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'X-CSRF-Token'],
)

# Include routers
app.include_router(auth_router)
app.include_router(dataset_router)
app.include_router(feedback_router)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'datapilot-ai-api', 'version': '1.0.0'}


@app.get('/api/settings/providers')
def providers():
    return {
        'providers': [
            {'id': 'openai', 'configured': bool(settings.openai_api_key), 'model': settings.openai_model},
            {'id': 'gemini', 'configured': bool(settings.gemini_api_key), 'model': settings.gemini_model},
        ]
    }
