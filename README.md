# AEGIS v2 API - Production Deployment

## Architecture

- **Frontend**: Lovable → Vercel (Next.js)
- **API**: Render Web Service (FastAPI)
- **Worker**: Render Background Worker (separate process)
- **Database**: Neon Postgres (multi-tenant)
- **Cache**: Upstash Redis

## Quick Deploy (2h)

### 1. Database (Neon)

```bash
# Go to https://neon.tech
# Create account → New Project → "aegis-v2"
# Copy DATABASE_URL
# Run migrations:
psql $DATABASE_URL < database_schema.sql
```

### 2. Redis (Upstash)

```bash
# Go to https://upstash.com
# Create account → New Database → "aegis-cache"
# Copy REDIS_URL
```

### 3. GitHub

```bash
cd ~/aegis-v2-api
git init
git add .
git commit -m "Initial AEGIS v2 API"
gh repo create aegis-v2-api --public --source=. --remote=origin --push
```

### 4. Render

```bash
# Go to https://render.com
# New → Blueprint → Connect GitHub repo
# render.yaml will auto-configure API + Worker
# Add env vars:
#   - DATABASE_URL (from Neon)
#   - REDIS_URL (from Upstash)
#   - OPENAI_API_KEY (optional)
```

### 5. Verify

```bash
curl https://aegis-v2-api.onrender.com/health
# Should return: {"status": "healthy", "checks": {"api": "ok", "postgres": "ok", "redis": "ok"}}
```

### 6. Frontend (Lovable → Vercel)

```bash
# In Lovable project:
# Settings → Environment Variables → Add:
#   NEXT_PUBLIC_API_URL=https://aegis-v2-api.onrender.com
# Deploy → Sync to GitHub → Connect Vercel
```

## Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set env vars
export DATABASE_URL="postgresql://..."
export REDIS_URL="redis://..."

# Run API
uvicorn app.main:app --reload --port 8000

# Run Worker (separate terminal)
python worker.py
```

## Monitoring

- **Logs**: Render Dashboard → Logs
- **Metrics**: `/health` endpoint
- **Database**: Neon Dashboard → Monitoring

## Non-Negotiables ✅

1. ✅ API and Worker separated
2. ✅ Migrations idempotent (schema.sql)
3. ✅ tenant_id everywhere
4. ✅ Queue with idempotency (run_id)
5. ✅ Observability (/health, structured logs)
