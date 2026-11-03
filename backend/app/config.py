from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str
    # The CRM keeps all its tables in this schema, so it can share Geohub's database without touching its tables.
    db_schema: str = "crm"
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

    # Printed on every invoice. Change them here (as variables) if they ever change.
    company_name: str = "GeoEstate NIG Limited"
    company_address: str = "1, Agonbako Street, behind Community Secondary School, Kabusa, FCT, Nigeria"
    company_rc: str = "9631300"
    company_tin: str = "2623706767701"
    company_email: str = "geoestate.ng@gmail.com"
    company_phone: str = ""
    bank_name: str = "Guaranty Trust Bank (GTB)"
    bank_account_name: str = "GEOESTATE NIG LIMITED"
    bank_account_number: str = "3005285279"
    vat_rate: float = 7.5                      # percent, for new invoices
    invoice_due_days: int = 14                 # days to pay, from the issue date
    invoice_prefix: str = "GE"                 # invoice numbers: GE-2026-0001

    # The link to Geohub: its address, and the key that must equal CRM_LINK_KEY there. Empty = not linked.
    geohub_url: str = ""
    geohub_api_prefix: str = "/api"
    geohub_link_key: str = ""

    rate_limit_enabled: bool = True
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _checks(self):
        self.app_url = self.app_url.strip().rstrip("/")
        self.geohub_url = self.geohub_url.strip().rstrip("/")
        self.geohub_link_key = self.geohub_link_key.strip()
        if not self.db_schema.isidentifier() or self.db_schema.lower() == "public":
            raise ValueError("DB_SCHEMA must be a plain name other than public, e.g. crm")
        if self.env == "prod" and (len(self.jwt_secret) < 32 or self.jwt_secret.startswith("change-me")):
            raise ValueError("JWT_SECRET must be a random string of 32+ characters when ENV=prod")
        return self


settings = Settings()
