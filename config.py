import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model_id: str = os.getenv("MODEL_ID", "claude-opus-4-6")
    sources_file: str = os.getenv("SOURCES_FILE", "sources.txt")
    output_dir: str = os.getenv("OUTPUT_DIR", "output")
    max_tokens_filter: int = 100
    max_tokens_rewrite: int = 400
    token_budget: int = int(os.getenv("TOKEN_BUDGET", "50000"))
    request_delay_seconds: float = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "4"))
    schedule_day: str = "fri"
    schedule_hour: int = int(os.getenv("SCHEDULE_HOUR", "15"))
    schedule_minute: int = int(os.getenv("SCHEDULE_MINUTE", "0"))
    schedule_timezone: str = os.getenv("SCHEDULE_TIMEZONE", "Asia/Kolkata")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    email_sender: str = os.getenv("EMAIL_SENDER", "")
    email_app_password: str = os.getenv("EMAIL_APP_PASSWORD", "")
    email_recipients: str = os.getenv("EMAIL_RECIPIENTS", "")


config = Config()

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
