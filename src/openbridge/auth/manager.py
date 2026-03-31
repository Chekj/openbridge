"""Authentication manager."""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional

import jwt

from openbridge.config import Config


class AuthManager:
    """Manages authentication and authorization."""

    def __init__(self, config: Config):
        self.config = config
        self.secret = config.security.jwt_secret
        self._sessions: dict[str, dict] = {}

    def create_token(self, user_id: str, platform: str, expires_in: int = 3600) -> str:
        """Create a JWT token for a user."""
        payload = {
            "user_id": user_id,
            "platform": platform,
            "exp": time.time() + expires_in,
            "iat": time.time(),
            "jti": secrets.token_hex(16),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def is_command_allowed(self, command: str) -> bool:
        """Check if a command is allowed."""
        allowed = self.config.security.allowed_commands
        blocked = self.config.security.blocked_commands

        # Check blocked commands
        for pattern in blocked:
            if self._match_pattern(command, pattern):
                return False

        # Check allowed commands
        if "*" in allowed:
            return True

        for pattern in allowed:
            if self._match_pattern(command, pattern):
                return True

        return False

    def _match_pattern(self, text: str, pattern: str) -> bool:
        """Match text against a glob pattern."""
        import fnmatch

        return fnmatch.fnmatch(text, pattern)

    def hash_password(self, password: str) -> str:
        """Hash a password."""
        salt = secrets.token_hex(16)
        pwdhash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return salt + pwdhash.hex()

    def verify_password(self, password: str, hash_str: str) -> bool:
        """Verify a password against a hash."""
        salt = hash_str[:32]
        stored_hash = hash_str[32:]
        pwdhash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return pwdhash.hex() == stored_hash
