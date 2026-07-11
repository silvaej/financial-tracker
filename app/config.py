from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+psycopg2://finance:finance@localhost:5432/finance_tracker"
    secret_key: str = "dev-secret-change-me"


settings = Settings()
