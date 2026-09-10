"""Profile storage: a single JSON file, chmod 600, plus the active-profile marker."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Dict, Optional


def config_dir() -> Path:
    base = os.environ.get("GITP_HOME")
    if base:
        return Path(base).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return root / "gitp"


@dataclass
class Profile:
    name: str
    user_name: str
    email: str
    ssh_key: Optional[str] = None
    login: Optional[str] = None
    gh_user: Optional[str] = None
    isolate_ssh_config: bool = False
    signing_key: Optional[str] = None
    host: str = "github.com"
    token: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "Profile":
        known = {f.name for f in fields(cls)} - {"name"}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(name=name, **kwargs)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("name")
        return {k: v for k, v in d.items() if v not in (None, {}, "")}

    def credential_login(self) -> str:
        """Username for the host's credential line; the token is what actually authenticates."""
        return self.login or self.user_name

    def key_path(self) -> Optional[Path]:
        return Path(self.ssh_key).expanduser() if self.ssh_key else None


class Store:
    """All profiles in <config>/profiles.json; the active name in <config>/active."""

    def __init__(self, directory: Optional[Path] = None):
        self.dir = directory or config_dir()
        self.path = self.dir / "profiles.json"
        self.active_path = self.dir / "active"

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with self.path.open() as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"gitp: {self.path} is not valid JSON ({exc})")

    def profiles(self) -> Dict[str, Profile]:
        return {n: Profile.from_dict(n, d) for n, d in sorted(self._load_raw().items())}

    def get(self, name: str) -> Profile:
        raw = self._load_raw()
        if name not in raw:
            known = ", ".join(sorted(raw)) or "none yet"
            raise SystemExit(f"gitp: no profile named {name!r} (have: {known})")
        return Profile.from_dict(name, raw[name])

    def save(self, profile: Profile) -> None:
        raw = self._load_raw()
        raw[profile.name] = profile.to_dict()
        self._write(raw)

    def delete(self, name: str) -> None:
        raw = self._load_raw()
        if name not in raw:
            raise SystemExit(f"gitp: no profile named {name!r}")
        del raw[name]
        self._write(raw)
        if self.active() == name:
            self.active_path.unlink(missing_ok=True)

    def _write(self, raw: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        tmp = self.path.with_suffix(".json.tmp")
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            json.dump(raw, fh, indent=2, sort_keys=True)
            fh.write("\n")
        tmp.replace(self.path)
        os.chmod(self.path, 0o600)

    def active(self) -> Optional[str]:
        if not self.active_path.exists():
            return None
        return self.active_path.read_text().strip() or None

    def set_active(self, name: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.active_path.write_text(name + "\n")
