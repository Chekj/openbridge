"""Configuration management for OpenBridge."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, validator


class SecurityConfig(BaseModel):
    """Security configuration."""

    jwt_secret: str = Field(default_factory=lambda: os.urandom(32).hex())
    session_timeout: int = 3600
    max_sessions_per_user: int = 3
    allowed_commands: list[str] = Field(default_factory=lambda: ["*"])
    blocked_commands: list[str] = Field(default_factory=list)
    require_auth: bool = True
    encryption_enabled: bool = False


class TelegramAdapterConfig(BaseModel):
    """Telegram adapter configuration."""

    enabled: bool = False
    bot_token: Optional[str] = None
    allowed_users: list[int] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    polling_timeout: int = 30


class DiscordAdapterConfig(BaseModel):
    """Discord adapter configuration."""

    enabled: bool = False
    bot_token: Optional[str] = None
    guild_id: Optional[str] = None
    allowed_roles: list[str] = Field(default_factory=list)
    command_prefix: str = "!"


class WhatsAppAdapterConfig(BaseModel):
    """WhatsApp adapter configuration."""

    enabled: bool = False
    session_path: str = ".whatsapp_session"
    webhook_url: Optional[str] = None


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    reload: bool = False
    log_level: str = "INFO"


class RedisConfig(BaseModel):
    """Redis configuration."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    enabled: bool = True
    commands_per_minute: int = 30
    messages_per_second: int = 5
    burst_size: int = 10


class FeaturesConfig(BaseModel):
    """Feature flags configuration."""

    file_transfer: bool = True
    session_persistence: bool = True
    auto_cleanup: bool = True
    rate_limiting: RateLimitConfig = Field(default_factory=RateLimitConfig)


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5


class Config(BaseModel):
    """Main configuration class."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    adapters: dict[str, Any] = Field(default_factory=dict)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    data_dir: str = Field(default="~/.openbridge")

    @validator("adapters", pre=True, always=True)
    def validate_adapters(cls, v):
        """Validate and convert adapter configs."""
        if not v:
            return {
                "telegram": TelegramAdapterConfig(),
                "discord": DiscordAdapterConfig(),
                "whatsapp": WhatsAppAdapterConfig(),
            }

        adapters = {}
        for name, config in v.items():
            if name == "telegram":
                adapters[name] = (
                    TelegramAdapterConfig(**config) if isinstance(config, dict) else config
                )
            elif name == "discord":
                adapters[name] = (
                    DiscordAdapterConfig(**config) if isinstance(config, dict) else config
                )
            elif name == "whatsapp":
                adapters[name] = (
                    WhatsAppAdapterConfig(**config) if isinstance(config, dict) else config
                )
            else:
                adapters[name] = config
        return adapters

    @classmethod
    def from_file(cls, path: Path | str) -> Config:
        """Load configuration from YAML file."""
        path = Path(path).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        # Expand environment variables
        data = cls._expand_env_vars(data)

        return cls(**data)

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        config = cls()

        # Server config
        if host := os.getenv("OB_SERVER_HOST"):
            config.server.host = host
        if port := os.getenv("OB_SERVER_PORT"):
            config.server.port = int(port)

        # Security config
        if secret := os.getenv("OB_JWT_SECRET"):
            config.security.jwt_secret = secret

        # Telegram
        if token := os.getenv("OB_TELEGRAM_TOKEN"):
            config.adapters["telegram"].enabled = True
            config.adapters["telegram"].bot_token = token

        # Discord
        if token := os.getenv("OB_DISCORD_TOKEN"):
            config.adapters["discord"].enabled = True
            config.adapters["discord"].bot_token = token

        # Redis
        if os.getenv("OB_REDIS_ENABLED", "false").lower() == "true":
            config.redis.enabled = True
            if host := os.getenv("OB_REDIS_HOST"):
                config.redis.host = host
            if port := os.getenv("OB_REDIS_PORT"):
                config.redis.port = int(port)

        return config

    @staticmethod
    def _expand_env_vars(obj: Any) -> Any:
        """Recursively expand environment variables in config."""
        if isinstance(obj, dict):
            return {k: Config._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Config._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            default = None
            if ":-" in env_var:
                env_var, default = env_var.split(":-", 1)
            return os.getenv(env_var, default)
        return obj

    def to_file(self, path: Path | str) -> None:
        """Save configuration to YAML file."""
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)

    def get_data_dir(self) -> Path:
        """Get the data directory path."""
        return Path(self.data_dir).expanduser()

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        data_dir = self.get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "sessions").mkdir(exist_ok=True)
        (data_dir / "logs").mkdir(exist_ok=True)


def get_default_config() -> Config:
    """Get default configuration."""
    return Config()
