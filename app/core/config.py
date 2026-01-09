from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    AEGIS_ENV: str = "production"
    GIT_TAG: str = "2.0.0"
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: Optional[str] = None
    
    # API Keys (for AI services)
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # FinOps limits (USD)
    FINOPS_SOFT_LIMIT_STARTER: int = 12
    FINOPS_SOFT_LIMIT_PRO: int = 35
    FINOPS_SOFT_LIMIT_ENTERPRISE: int = 90
    
    FINOPS_HARD_LIMIT_STARTER: int = 20
    FINOPS_HARD_LIMIT_PRO: int = 60
    FINOPS_HARD_LIMIT_ENTERPRISE: int = 150
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
