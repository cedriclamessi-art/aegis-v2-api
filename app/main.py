from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog
import os
from typing import Optional
import asyncpg
import redis.asyncio as redis

logger = structlog.get_logger()

app = FastAPI(
    title="AEGIS v2 API",
    version="2.0.0",
    description="Production-ready API for AEGIS multi-tenant pipeline"
)

# CORS - Allow Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://*.vercel.app",
        "https://*.lovable.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup():
    global db_pool, redis_client
    
    # Connect to Postgres
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    logger.info("postgres_connected", pool_size=10)
    
    # Connect to Redis
    REDIS_URL = os.getenv("REDIS_URL")
    if REDIS_URL:
        redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("redis_connected")
    else:
        logger.warning("redis_not_configured")

@app.on_event("shutdown")
async def shutdown():
    global db_pool, redis_client
    if db_pool:
        await db_pool.close()
    if redis_client:
        await redis_client.close()

@app.get("/health")
async def health():
    """Health check endpoint for Render"""
    checks = {"api": "ok"}
    
    # Check Postgres
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["postgres"] = "ok"
        except Exception as e:
            checks["postgres"] = f"error: {str(e)}"
    
    # Check Redis
    if redis_client:
        try:
            await redis_client.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {str(e)}"
    
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}

# Models
class OnboardingRequest(BaseModel):
    tenant_id: str
    revenue_monthly: int
    ad_budget_monthly: int
    target_countries: list[str]
    product_count: int

class ProfileResponse(BaseModel):
    profile: str
    monthly_price_eur: int
    features: dict
    reason: str

@app.post("/api/v2/onboarding", response_model=ProfileResponse)
async def onboarding(req: OnboardingRequest):
    """Profile selection based on AEGIS config rules"""
    logger.info("onboarding_start", tenant_id=req.tenant_id)
    
    # Rule-based selection (from config)
    if req.revenue_monthly > 50000:
        profile = "enterprise"
        reason = "revenue > 50k"
    elif req.ad_budget_monthly > 5000:
        profile = "pro"
        reason = "ad_budget > 5k"
    elif len(req.target_countries) > 3:
        profile = "enterprise"
        reason = "multi-country"
    elif req.product_count > 5:
        profile = "pro"
        reason = "product_count > 5"
    else:
        profile = "starter"
        reason = "default"
    
    # Profile details
    profiles = {
        "starter": {"price": 79, "features": {"videos": False, "mlops": False}},
        "pro": {"price": 249, "features": {"videos": True, "mlops": False}},
        "enterprise": {"price": 990, "features": {"videos": True, "mlops": True}}
    }
    
    selected = profiles[profile]
    
    # Store in DB
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aegis.tenants (tenant_id, profile, revenue_monthly, ad_budget_monthly, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET profile = $2, updated_at = NOW()
            """,
            req.tenant_id, profile, req.revenue_monthly, req.ad_budget_monthly
        )
    
    logger.info("onboarding_complete", tenant_id=req.tenant_id, profile=profile)
    
    return ProfileResponse(
        profile=profile,
        monthly_price_eur=selected["price"],
        features=selected["features"],
        reason=reason
    )

class PipelineRequest(BaseModel):
    tenant_id: str
    store_id: str
    product_data: dict

@app.post("/api/v2/pipeline/run")
async def run_pipeline(req: PipelineRequest):
    """Enqueue pipeline run (processed by worker)"""
    logger.info("pipeline_enqueue", tenant_id=req.tenant_id, store_id=req.store_id)
    
    # Generate run_id
    import uuid
    run_id = str(uuid.uuid4())
    
    # Store in manifest_v2_index
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aegis.manifest_v2_index 
            (tenant_id, store_id, run_id, status, created_at)
            VALUES ($1, $2, $3, 'queued', NOW())
            """,
            req.tenant_id, req.store_id, run_id
        )
    
    # Enqueue to Redis
    if redis_client:
        import json
        await redis_client.lpush(
            "aegis:pipeline:queue",
            json.dumps({
                "run_id": run_id,
                "tenant_id": req.tenant_id,
                "store_id": req.store_id,
                "product_data": req.product_data
            })
        )
    
    logger.info("pipeline_queued", run_id=run_id)
    
    return {"run_id": run_id, "status": "queued"}

@app.get("/api/v2/manifest/{tenant_id}/{store_id}")
async def get_manifest(tenant_id: str, store_id: str):
    """Get latest manifest for store"""
    async with db_pool.acquire() as conn:
        # Get latest run
        row = await conn.fetchrow(
            """
            SELECT run_id, status, deploy_ready, created_at
            FROM aegis.manifest_v2_index
            WHERE tenant_id = $1 AND store_id = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            tenant_id, store_id
        )
        
        if not row:
            raise HTTPException(404, "No manifest found")
        
        # Get modules
        modules = await conn.fetch(
            """
            SELECT module_name, module_data
            FROM aegis.manifest_v2_modules
            WHERE run_id = $1
            """,
            row["run_id"]
        )
        
        return {
            "run_id": row["run_id"],
            "status": row["status"],
            "deploy_ready": row["deploy_ready"],
            "created_at": row["created_at"].isoformat(),
            "modules": {m["module_name"]: m["module_data"] for m in modules}
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
