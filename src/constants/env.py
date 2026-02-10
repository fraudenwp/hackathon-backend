##
## WARNING: Do not make any changes to this file
## This file is used to set the environment variables
## The variables are used in the development and production environment
##
import os

from dotenv import load_dotenv

load_dotenv()


BASE_URL = os.getenv("BASE_URL", "http://localhost:8004")

ENV_NAME = "DEV"

if "production" in BASE_URL:
    ENV_NAME = "PRODUCTION"


# Check if VALKEY_WORKER_URL is provided directly (e.g., from Terraform/ECS)
VALKEY_WORKER_URL = os.getenv("VALKEY_WORKER_URL", "redis://valkey-worker:6379")

# If not provided, construct from individual components


# Helper function to construct Valkey URL with specific database index
# Handles cases where VALKEY_WORKER_URL might already contain a database path
def _get_valkey_url_with_db(base_url: str, db_index: int) -> str:
    """
    Constructs a Valkey URL with a specific database index.
    Strips any existing database path from the base URL to prevent invalid URLs
    like redis://host:6379/5/0 (if base URL already had /5).

    Args:
        base_url: Base Valkey URL (e.g., redis://host:6379 or redis://host:6379/5)
        db_index: Database index to use (0-15)

    Returns:
        Valkey URL with the specified database index (e.g., redis://host:6379/2)
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(base_url)
    # Remove any existing database path
    base_path = ""
    # Reconstruct URL without database path
    base_url_clean = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            base_path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    return f"{base_url_clean}/{db_index}"


VALKEY_WEBSOCKET_URL = _get_valkey_url_with_db(VALKEY_WORKER_URL, 5)

# Database configuration - construct from individual env vars if available (AWS)
# Otherwise fall back to DATABASE_URL or default (local development)
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_SECRET_ARN = os.getenv(
    "DB_SECRET_ARN"
)  # AWS Secrets Manager ARN for credential rotation

if DB_HOST and DB_USER and DB_PASSWORD and DB_NAME:
    # AWS environment - construct from individual variables
    DATABASE_URL = (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
else:
    # Local development or DATABASE_URL provided directly
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/talenterai"
    )

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
)
SECRET_KEY_ENCRYPTION = os.environ.get(
    "SECRET_KEY_ENCRYPTION", "B1xNfUQz9c2E9JHgW8Tf7kLzVZqcVGRlfKsff5HQZlI="
)

MEDIA_URL_PREFIX = os.environ.get(
    "MEDIA_URL_PREFIX", "http://localhost:8004/media/download/"
)


DEVELOPMENT = os.environ.get("DEVELOPMENT", False)

COMMAND = os.environ.get("COMMAND", "unknown")


JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt_access_token")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = os.environ.get("JWT_EXPIRATION_MINUTES", 30)


FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "https://localhost:3000")

R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "r2_access_key_id")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "r2_secret_access_key")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "r2_account_id")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "r2_bucket_name")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "r2_endpoint_url")
R2_REGION_NAME = os.getenv("R2_REGION_NAME", "auto")

WIROAI_API_KEY = os.getenv("WIROAI_API_KEY", "")
WIROAI_API_SECRET = os.getenv("WIROAI_API_SECRET", "")
