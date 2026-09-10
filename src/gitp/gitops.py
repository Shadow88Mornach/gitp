"""The side effects: git config, ssh-agent, and the credential file."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from .store import Profile

CRED_FILE = Path.home() / ".git-credentials"


def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def in_repo() -> bool:
    try:
        run(["git", "rev-parse", "--git-dir"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _scope(local: bool) -> str:
    return "--local" if local else "--global"


def git_set(key: str, value: Optional[str], local: bool) -> None:
    scope = _scope(local)
    if value:
        run(["git", "config", scope, key, value])
    else:
        run(["git", "config", scope, "--unset-all", key], check=False)


def git_get(key: str, local: bool = False) -> Optional[str]:
    proc = run(["git", "config", _scope(local), "--get", key], check=False)
    return proc.stdout.strip() or None


def ssh_command(key: Path, isolate: bool = False) -> str:
    """Build core.sshCommand.

    IdentityFile in ~/.ssh/config is *additive* and wins over -i, so a static
    `Host github.com / IdentityFile ...` block silently overrides the profile's key.
    `isolate` drops the user's ssh config (-F /dev/null) so only this key is offered.
    """
    prefix = "ssh -F /dev/null" if isolate else "ssh"
    return f'{prefix} -i "{key}" -o IdentitiesOnly=yes'


def load_key(key: Path) -> str:
    """Drop other identities from the agent and add this one. Returns a status line."""
    if not key.exists():
        return f"ssh key {key} not found — skipped ssh-agent"
    if not os.environ.get("SSH_AUTH_SOCK"):
        return "no ssh-agent running — skipped ssh-add"
    run(["ssh-add", "-D"], check=False)
    proc = run(["ssh-add", str(key)], check=False)
    if proc.returncode != 0:
        return f"ssh-add failed: {proc.stderr.strip()}"
    return f"loaded {key} into ssh-agent"


def write_credential(profile: Profile) -> Optional[str]:
    """Keep exactly one credential line per host in ~/.git-credentials."""
    if not profile.token:
        return None
    line = f"https://{quote(profile.credential_login(), safe='')}:{quote(profile.token, safe='')}@{profile.host}"
    existing = CRED_FILE.read_text().splitlines() if CRED_FILE.exists() else []
    kept = [l for l in existing if l.strip() and not l.rstrip("/").endswith("@" + profile.host)]
    fd = os.open(CRED_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w") as fh:
        fh.write("\n".join(kept + [line]) + "\n")
    os.chmod(CRED_FILE, 0o600)
    return f"token written to {CRED_FILE} for {profile.host}"


def switch_gh(user: str) -> str:
    """Point the gh CLI at the matching account, if gh is installed."""
    proc = run(["gh", "auth", "switch", "-h", "github.com", "-u", user], check=False)
    if proc.returncode != 0:
        return f"gh auth switch -u {user} failed: {(proc.stderr or proc.stdout).strip()}"
    return f"gh CLI now using {user}"


def apply(profile: Profile, local: bool) -> List[str]:
    log = []
    git_set("user.name", profile.user_name, local)
    git_set("user.email", profile.email, local)
    log.append(f"user.name={profile.user_name}  user.email={profile.email}")

    key = profile.key_path()
    if key:
        git_set("core.sshCommand", ssh_command(key, profile.isolate_ssh_config), local)
        log.append(f"core.sshCommand -> {key}" + ("  (isolated from ~/.ssh/config)" if profile.isolate_ssh_config else ""))
        log.append(load_key(key))
    else:
        git_set("core.sshCommand", None, local)

    if profile.signing_key:
        git_set("user.signingkey", profile.signing_key, local)
        git_set("commit.gpgsign", "true", local)
        log.append(f"signing key {profile.signing_key} (commit.gpgsign=true)")
    else:
        git_set("user.signingkey", None, local)
        git_set("commit.gpgsign", None, local)

    if profile.token:
        git_set("credential.helper", "store", local)
        msg = write_credential(profile)
        if msg:
            log.append(msg)

    if profile.gh_user:
        log.append(switch_gh(profile.gh_user))

    for key_name, value in (profile.extra or {}).items():
        git_set(key_name, value, local)
        log.append(f"{key_name}={value}")
    return log
