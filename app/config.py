from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": .env also carries POSTGRES_* keys that only
    # docker-compose.yml's own variable substitution reads, not this app.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://finance:finance@localhost:5432/finance_tracker"
    secret_key: str = "dev-secret-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""


settings = Settings()
