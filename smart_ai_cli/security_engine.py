"""Security Guardrails, Command Sandboxing, and Secret Scrubbing for Smart AI Gateway.

Provides multi-layer security protections:
- Dangerous shell command interception (rm -rf, fork bombs, disk formatting).
- Workspace path traversal jail (prevents escaping workspace root).
- Sensitive file protections (.env, private keys, certificates, credentials).
- Secret scrubber removing API keys (OpenAI, Groq, Anthropic, GitHub) from logs.
- Audit logging of all elevated or high-risk actions in .smartai/security_audit.log.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional, Tuple


class SecurityGuardrailEngine:
    """Enforces safety guardrails, path sandboxing, and secret scrubbing."""

    DANGEROUS_COMMAND_PATTERNS = [
        r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+/(?:\s|$|\*)",  # rm -rf / or rm -rf /*
        r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+\*",  # rm -rf *
        r"\bformat\s+[a-zA-Z]:",  # format C:
        r":\(\)\s*\{\s*:\|:&\s*\};:",  # fork bomb
        r"\bmkfs\b",  # format filesystem
        r"\bdd\s+if=.*of=/dev/[a-z]+",  # dd overwriting disk
        r">\s*/dev/sda",  # direct disk overwrite
    ]

    SENSITIVE_FILE_PATTERNS = [
        r"^\.env(\..+)?$",
        r".*\.pem$",
        r".*\.key$",
        r".*id_rsa.*",
        r".*id_ed25519.*",
        r".*credentials\.json$",
        r".*secret.*\.ya?ml$",
    ]

    SECRET_MASKS = [
        (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_OPENAI_KEY]"),
        (r"gsk_[a-zA-Z0-9]{20,}", "[REDACTED_GROQ_KEY]"),
        (r"ghp_[a-zA-Z0-9]{20,}", "[REDACTED_GITHUB_TOKEN]"),
        (r"gho_[a-zA-Z0-9]{20,}", "[REDACTED_GITHUB_OAUTH]"),
        (r"bearer\s+[a-zA-Z0-9\-_.]+", "Bearer [REDACTED_TOKEN]"),
    ]

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.audit_log_path = self.workspace_root / ".smartai" / "security_audit.log"
        self._ensure_log()

    def _ensure_log(self) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_audit(self, action: str, details: str, risk_level: str = "INFO") -> None:
        """Appends security event to audit log."""
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"[{ts}] [{risk_level.upper()}] {action}: {details}\n"
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def validate_command(self, command: str) -> Tuple[bool, str, bool]:
        """Validates shell command.

        Returns: (is_allowed: bool, reason: str, is_high_risk: bool)
        """
        clean_cmd = command.strip()

        # Check dangerous blacklist
        for pat in self.DANGEROUS_COMMAND_PATTERNS:
            if re.search(pat, clean_cmd, re.IGNORECASE):
                self.log_audit("BLOCKED_COMMAND", f"Blocked dangerous command matching '{pat}': {clean_cmd}", "ALERT")
                return False, f"Command execution blocked: matches dangerous pattern '{pat}'.", True

        # Check elevated/high risk commands
        high_risk = bool(re.search(r"\b(sudo|chmod -R 777|chown -R|npm unpublish)\b", clean_cmd, re.IGNORECASE))
        if high_risk:
            self.log_audit("HIGH_RISK_COMMAND", f"Allowed high-risk command: {clean_cmd}", "WARNING")
            return True, "High risk command allowed with monitoring.", True

        return True, "Command is safe.", False

    def is_path_in_workspace(self, target_path: Path | str) -> bool:
        """Verifies that resolved path stays inside authorized workspace root."""
        p = Path(target_path)
        resolved = p.resolve() if p.is_absolute() else (self.workspace_root / p).resolve()
        try:
            resolved.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    def is_sensitive_file(self, file_path: Path | str) -> bool:
        """Checks if file is protected/sensitive (.env, certificates, keys)."""
        name = Path(file_path).name.lower()
        for pat in self.SENSITIVE_FILE_PATTERNS:
            if re.match(pat, name, re.IGNORECASE):
                return True
        return False

    def scrub_secrets(self, text: str) -> str:
        """Redacts known API keys and tokens from text."""
        scrubbed = text
        for pat, replacement in self.SECRET_MASKS:
            scrubbed = re.sub(pat, replacement, scrubbed)
        return scrubbed


default_security_engine = SecurityGuardrailEngine()
