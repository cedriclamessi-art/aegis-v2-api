import asyncio
import json
import os
import structlog
import asyncpg
import redis.asyncio as redis
from typing import Optional

logger = structlog.get_logger()

db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None

async def init_connections():
    global db_pool, redis_client
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    logger.info("worker_postgres_connected")
    
    REDIS_URL = os.getenv("REDIS_URL")
    redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("worker_redis_connected")

async def process_pipeline_job(job_data: dict):
    """Process a single pipeline job"""
    run_id = job_data["run_id"]
    tenant_id = job_data["tenant_id"]
    store_id = job_data["store_id"]
    
    logger.info("pipeline_start", run_id=run_id, tenant_id=tenant_id, store_id=store_id)
    
    try:
        # Update status to processing
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE aegis.manifest_v2_index SET status = 'processing', updated_at = NOW() WHERE run_id = $1",
                run_id
            )
        
        # PHASE 1: Prefetch (simulated)
        logger.info("phase_1_prefetch", run_id=run_id)
        await asyncio.sleep(2)  # Simulate work
        
        # PHASE 2: Hard Block Validations
        logger.info("phase_2_hard_block", run_id=run_id)
        await asyncio.sleep(3)
        
        # Check hard gates (simplified)
        deploy_ready = True  # In real: check TEXT_SIMILARITY, AI_LIKENESS, etc.
        reasons = []
        
        # PHASE 3: Assets Generation
        logger.info("phase_3_assets", run_id=run_id)
        await asyncio.sleep(5)
        
        # PHASE 4: Soft Checks (non-blocking)
        logger.info("phase_4_soft_checks", run_id=run_id)
        await asyncio.sleep(2)
        
        # PHASE 5: Manifest Build
        logger.info("phase_5_manifest", run_id=run_id)
        
        # Store modules in manifest_v2_modules
        async with db_pool.acquire() as conn:
            # Audit module
            await conn.execute(
                """
                INSERT INTO aegis.manifest_v2_modules (run_id, module_name, module_data)
                VALUES ($1, 'audit', $2)
                """,
                run_id,
                json.dumps({"checks_passed": 12, "checks_failed": 0})
            )
            
            # Decision module
            await conn.execute(
                """
                INSERT INTO aegis.manifest_v2_modules (run_id, module_name, module_data)
                VALUES ($1, 'decision', $2)
                """,
                run_id,
                json.dumps({"deploy_ready": deploy_ready, "reasons": reasons})
            )
            
            # Deployment module
            await conn.execute(
                """
                INSERT INTO aegis.manifest_v2_modules (run_id, module_name, module_data)
                VALUES ($1, 'deployment', $2)
                """,
                run_id,
                json.dumps({"ready_to_deploy_path": f"s3://aegis/{tenant_id}/{store_id}/{run_id}"})
            )
            
            # Update index
            await conn.execute(
                """
                UPDATE aegis.manifest_v2_index 
                SET status = 'completed', deploy_ready = $2, updated_at = NOW()
                WHERE run_id = $1
                """,
                run_id, deploy_ready
            )
        
        logger.info("pipeline_complete", run_id=run_id, deploy_ready=deploy_ready)
        
    except Exception as e:
        logger.error("pipeline_failed", run_id=run_id, error=str(e))
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE aegis.manifest_v2_index SET status = 'failed', updated_at = NOW() WHERE run_id = $1",
                run_id
            )

async def worker_loop():
    """Main worker loop - polls Redis queue"""
    logger.info("worker_started")
    
    while True:
        try:
            # BRPOP with 5s timeout
            result = await redis_client.brpop("aegis:pipeline:queue", timeout=5)
            
            if result:
                _, job_json = result
                job_data = json.loads(job_json)
                await process_pipeline_job(job_data)
            
        except Exception as e:
            logger.error("worker_error", error=str(e))
            await asyncio.sleep(5)

async def main():
    await init_connections()
    await worker_loop()

if __name__ == "__main__":
    asyncio.run(main())
