from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "meeting_intelligence"
    api_prefix: str = "/api"
    # Comma-separated browser origins (production: add https://your-app.vercel.app)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional regex, e.g. https://.*\.vercel\.app for all preview deployments
    cors_origin_regex: str | None = None


settings = Settings()
