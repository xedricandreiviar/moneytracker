# Deploying Daily Money Tracker to Railway

## Architecture

This project deploys as **two Railway services** from one monorepo:

1. **Backend** (FastAPI + PostgreSQL) — `backend/` directory
2. **Frontend** (React static site) — `frontend/` directory
3. **PostgreSQL** — Railway managed database plugin

## Quick Deploy

### 1. Create a Railway project

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click "New Project" → "Deploy from GitHub Repo"
3. Select `xedricandreiviar/moneytracker`

### 2. Add PostgreSQL

1. In your Railway project, click "New" → "Database" → "PostgreSQL"
2. Railway will auto-provision and provide `DATABASE_URL`

### 3. Deploy the Backend

1. Click "New" → "GitHub Repo" → select `moneytracker`
2. In service settings:
   - **Root Directory**: `backend`
   - **Start Command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Add environment variables (Settings → Variables):
   - `DATABASE_URL` → copy from the PostgreSQL service (click the DB → Variables → `DATABASE_URL`)
   - `ALLOWED_ORIGINS` → `["https://your-frontend-domain.up.railway.app"]`
   - `JWT_SECRET_KEY` → generate a random secret (e.g., `openssl rand -hex 32`)
   - `VAPID_PRIVATE_KEY` → generate with `npx web-push generate-vapid-keys`
   - `VAPID_PUBLIC_KEY` → from the same command
   - `VAPID_CLAIMS_EMAIL` → `mailto:your@email.com`
   - `LLM_API_KEY` → your OpenAI API key (optional, for AI features)
   - `LLM_API_ENDPOINT` → `https://api.openai.com/v1/chat/completions`
   - `LLM_MODEL` → `gpt-4o-mini`
   - `SCHEDULER_ENABLED` → `true`

### 4. Deploy the Frontend

1. Click "New" → "GitHub Repo" → select `moneytracker` again
2. In service settings:
   - **Root Directory**: `frontend`
   - **Build Command**: `npm ci && npm run build`
   - **Start Command**: `npx serve dist -s -l $PORT`
3. Add environment variables:
   - `VITE_API_BASE_URL` → your backend Railway URL (e.g., `https://moneytracker-backend.up.railway.app`)

### 5. Connect the domains

1. Backend service: copy its public domain (e.g., `moneytracker-backend-production.up.railway.app`)
2. Frontend service: generate a public domain in Settings → Networking
3. Update backend `ALLOWED_ORIGINS` to include the frontend domain

## Environment Variables Reference

| Variable | Service | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | Backend | Yes | PostgreSQL connection string (auto from Railway DB) |
| `ALLOWED_ORIGINS` | Backend | Yes | JSON array of allowed CORS origins |
| `JWT_SECRET_KEY` | Backend | Yes | Secret for JWT tokens |
| `VAPID_PRIVATE_KEY` | Backend | Yes* | For push notifications |
| `VAPID_PUBLIC_KEY` | Backend | Yes* | For push notifications |
| `VAPID_CLAIMS_EMAIL` | Backend | Yes* | Contact email for VAPID |
| `LLM_API_KEY` | Backend | No | OpenAI API key for AI features |
| `LLM_API_ENDPOINT` | Backend | No | LLM API URL |
| `LLM_MODEL` | Backend | No | Model name |
| `SCHEDULER_ENABLED` | Backend | No | Enable background jobs (default: true) |
| `VITE_API_BASE_URL` | Frontend | Yes | Backend URL for API calls |

*Required for push notifications to work. App functions without them (falls back to in-app only).

## Generate VAPID Keys

```bash
npx web-push generate-vapid-keys
```

## Generate JWT Secret

```bash
openssl rand -hex 32
```

## Notes

- Railway auto-detects Python for the backend (via `requirements.txt`) and Node for the frontend (via `package.json`)
- The Procfile handles running migrations before starting the backend
- The frontend uses `serve` to serve the built static files with SPA fallback (`-s` flag)
- PostgreSQL is used in production (the app supports both MySQL and PostgreSQL via SQLAlchemy)
