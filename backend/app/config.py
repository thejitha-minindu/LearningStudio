from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./learning.db'
    provider_mode: str = 'fixture'
    dev_api_token: str = 'local-development-only'
    gemini_api_key: str = ''
    gemini_model: str = ''
    generator_provider: str = 'gemini'
    ollama_base_url: str = 'http://host.docker.internal:11434'
    ollama_model: str = 'qwen2.5:7b'
    tavily_api_key: str = ''
    max_searches: int = Field(3, ge=1, le=6)
    max_pages: int = Field(6, ge=1, le=12)
    max_download_bytes: int = Field(5_000_000, ge=1000, le=20_000_000)
    max_pdf_pages: int = Field(80, ge=1, le=200)
    request_timeout: int = Field(120, ge=1, le=300)
    retries: int = Field(2, ge=0, le=3)
    cache_seconds: int = Field(86400, ge=0)
    rate_limit_per_minute: int = Field(120, ge=1)
    allowed_resource_dir: str = ''
    cors_origins: str = 'http://localhost:3000'
    job_max_attempts: int = Field(3, ge=1, le=5)
    max_output_tokens: int = Field(6000, ge=1000, le=16000)


@lru_cache
def settings():
    return Settings()
