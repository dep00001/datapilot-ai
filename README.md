# DataPilot AI — Full-stack starter for a public-ready AI analytics product

DataPilot AI is a React + FastAPI starter for secure account registration, email OTP verification, password login/recovery, dataset upload, automatic profiling/EDA, interactive charts, AI-assisted dataset chat, exports, and feedback.

> This is a development foundation, not a security-audited production release. Before opening public registration, configure HTTPS, a transactional email provider, durable private file storage, PostgreSQL, backups, monitoring, abuse protection, and a security review.

## Architecture

- `frontend/`: React + TypeScript + Vite, responsive dark UI, CSS 3D visual effects, Plotly charts.
- `backend/`: FastAPI, SQLAlchemy, SQLite locally / PostgreSQL via `DATABASE_URL`, Argon2id password hashing, hashed OTPs and session tokens, ownership checks.
- CSV/XLSX uploads are stored under private backend storage and never served as public static files.
- Numerical summaries are calculated by Pandas; an AI provider only explains verified context.

## Requirements

- Python 3.11+
- Node.js 20+
- Optional: Resend API key for real verification emails; otherwise configure SMTP.
- Optional: OpenAI or Gemini API key for AI chat. Analytics/EDA works without an AI key.

## 1. Configure backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Windows: copy .env.example .env
```

Edit `.env`. Set a long random `APP_SECRET_KEY`, email provider credentials, and whichever AI provider you want. Never commit `.env`.

Run backend:

```bash
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Run backend smoke tests from the `backend/` directory with `python -m pytest -q`.

If email is not configured, registration intentionally fails to send and does not activate an account. Do not add a production OTP bypass. For local development, configure a test SMTP inbox or Resend test setup.

## 2. Configure frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The frontend proxies `/api` requests to FastAPI at `http://localhost:8000`.

## Environment variables

See `backend/.env.example`. Supported email providers: `resend` or `smtp`. Supported AI providers: `openai` and `gemini`. API keys stay on the backend only.

## Features implemented in this starter

- Registration with email OTP and expiry / resend / attempt limits
- Argon2id password hashing, hashed opaque session tokens, HttpOnly cookies
- Password login, logout, forgot-password and reset-password flows
- Dataset upload (CSV/XLSX), user-scoped private storage and preview
- Data profile, missing values, duplicate count, descriptive statistics, correlation matrix
- Cleaning preview/apply with a preserved original file and audit history metadata
- Interactive chart suggestions and Plotly visualizations
- Dataset chat using deterministic summaries plus optional OpenAI/Gemini explanation
- CSV and PDF report export
- Private feedback submission and own-feedback view
- Health endpoint and basic automated tests

## Before public launch — mandatory checklist

1. Use managed PostgreSQL and a durable private object store (not a single server's local disk).
2. Deploy behind HTTPS; set `COOKIE_SECURE=true` and exact `CORS_ORIGINS`.
3. Configure a verified sender domain and transactional email provider; test deliverability.
4. Set strong secrets in a secrets manager, not in source control.
5. Add a production-grade distributed rate limiter (e.g. Redis), WAF/abuse controls, monitoring, alerting, backups, and restore tests.
6. Add malware scanning and stricter upload limits for the expected workload.
7. Review privacy notice, terms, retention/deletion behavior, regional requirements, and provider data handling.
8. Review auth, CSRF, session invalidation, export permissions, and tenant isolation with security tests.
9. Configure worker/queue infrastructure for large files and long-running analyses.
10. Add admin roles and audited moderation before enabling public review publication. Feedback in this starter is private by default.

## Notes

- No application can guarantee every AI answer is correct. Numeric results are computed in Python; AI text should be checked.
- AI requests send only a limited profile/aggregate context by default, not the full uploaded file.
- Do not upload confidential or regulated information until your deployment and provider settings have been reviewed.
