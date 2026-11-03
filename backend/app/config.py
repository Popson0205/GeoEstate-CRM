from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str
    db_pool_max: int = 5
    jwt_secret: str
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    app_url: str = "http://localhost:5174"     # where staff open the CRM; links in emails point here
    api_prefix: str = ""                       # "/api" when one service serves the API and the built web app
    web_dir: str = ""                          # folder with the built web app; empty = API only
    cors_origins: str = "http://localhost:5174"

    # The first super admin: created on start-up if missing, and emailed a link to choose a password.
    super_admin_email: str = "geoestate.ng@gmail.com"
    super_admin_name: str = "GeoEstate Admin"

    # Email (Brevo over HTTPS, as in Geohub). Without a key, emails are written to the log instead.
    brevo_api_key: str = ""
    mail_from: str = "GeoEstate CRM <no-reply@geoestate.ng>"
    mail_reply_to: str = ""

    rate_limit_enabled: bool = True
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _checks(self):
        self.app_url = self.app_url.strip().rstrip("/")
        if self.env == "prod" and (len(self.jwt_secret) < 32 or self.jwt_secret.startswith("change-me")):
            raise ValueError("JWT_SECRET must be a random string of 32+ characters when ENV=prod")
        return self


settings = Settings()
