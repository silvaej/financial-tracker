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
    # Comma-separated allowlist gating /admin -- see issue #65. No is_admin
    # column/migration; a handful of operator emails doesn't need a
    # redeploy-free way to manage, revisit if that ever becomes false.
    admin_emails: str = ""

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(
            email.strip().lower() for email in self.admin_emails.split(",") if email.strip()
        )


settings = Settings()
