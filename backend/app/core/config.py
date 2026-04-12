"""Application configuration using pydantic-settings."""

import json
import logging
import os

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _resolve_database_url() -> str:
    """Build database URL from Secrets Manager if DATABASE_SECRET_ARN is set."""
    secret_arn = os.environ.get("DATABASE_SECRET_ARN")
    if not secret_arn:
        return os.environ.get(
            "MODERATION_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/moderation",
        )

    try:
        import boto3

        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(resp["SecretString"])
        host = secret["host"]
        port = secret.get("port", 5432)
        username = secret["username"]
        password = secret["password"]
        dbname = secret.get("dbname", "moderation")
        return f"postgresql://{username}:{password}@{host}:{port}/{dbname}"
    except Exception:
        logger.exception("Failed to resolve database URL from Secrets Manager")
        return "postgresql://postgres:postgres@localhost:5432/moderation"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Content Moderation API"
    debug: bool = False

    # Database
    database_url: str = _resolve_database_url()

    # AWS
    aws_region: str = "us-east-1"

    # API Key authentication
    api_keys: list[str] = []

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    cognito_region: str = "us-east-1"

    # SQS
    sqs_batch_test_queue_url: str = ""

    # S3
    s3_bucket_name: str = ""

    model_config = {"env_prefix": "MODERATION_", "env_file": ".env"}


settings = Settings()
