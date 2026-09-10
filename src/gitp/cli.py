"""gitp — swap git profiles (identity, SSH key, host token) in one command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import __version__, gitops
from .store import Profile, Store


def _mask(token: Optional[str]) -> str:
    if not token:
        return "-"
    return f"{token[:4]}…{token[-4:]}" if len(token) > 12 else "set"


def cmd_add(args, store: Store) -> int:
    existing = store.profiles().get(args.name)
    if existing and not args.force:
        raise SystemExit(f"gitp: profile {args.name!r} exists (use --force to overwrite)")

    token = args.token
    if args.token_stdin:
        token = sys.stdin.read().strip()

    profile = Profile(
        name=args.name,
        user_name=args.user_name,
        email=args.email,
        ssh_key=str(Path(args.ssh_key).expanduser()) if args.ssh_key else None,
        login=args.login,
        gh_user=args.gh_user,
        isolate_ssh_config=args.isolate_ssh_config,
        signing_key=args.signing_key,
        host=args.host,
        token=token,
    )
    key = profile.key_path()
    if key and not key.exists():
        print(f"gitp: warning — ssh key {key} does not exist yet", file=sys.stderr)
    store.save(profile)
    print(f"saved profile {profile.name!r}")
    return 0


def cmd_list(args, store: Store) -> int:
    profiles = store.profiles()
    if not profiles:
        print("no profiles yet — add one with: gitp add <name> --user-name … --email …")
        return 0
    active = store.active()
    width = max(len(n) for n in profiles)
    for name, p in profiles.items():
        mark = "*" if name == active else " "
        key = p.key_path().name if p.key_path() else "-"
        print(f"{mark} {name:<{width}}  {p.email:<28} key={key:<20} token={_mask(p.token)}")
    return 0


def cmd_show(args, store: Store) -> int:
    p = store.get(args.name)
    print(f"name        {p.name}")
    print(f"user.name   {p.user_name}")
    print(f"user.email  {p.email}")
    print(f"ssh key     {p.ssh_key or '-'}")
    print(f"signing key {p.signing_key or '-'}")
    print(f"login       {p.login or '(user.name)'}")
    print(f"gh user     {p.gh_user or '-'}")
    print(f"isolate ssh {p.isolate_ssh_config}")
    print(f"host        {p.host}")
    print(f"token       {_mask(p.token)}")
    for k, v in (p.extra or {}).items():
        print(f"{k:<11} {v}")
    return 0


def cmd_use(args, store: Store) -> int:
    profile = store.get(args.name)
    if args.local and not gitops.in_repo():
        raise SystemExit("gitp: --local needs to run inside a git repository")
    for line in gitops.apply(profile, local=args.local):
        print(f"  {line}")
    store.set_active(profile.name)
    scope = "this repo" if args.local else "global"
    print(f"switched to {profile.name!r} ({scope})")
    return 0


def cmd_current(args, store: Store) -> int:
    active = store.active()
    local = gitops.in_repo()
    name = gitops.git_get("user.name", local=False)
    email = gitops.git_get("user.email", local=False)
    print(f"active profile : {active or '(none recorded)'}")
    print(f"global identity: {name or '-'} <{email or '-'}>")
    print(f"global sshCommand: {gitops.git_get('core.sshCommand') or '-'}")
    if local:
        lname = gitops.git_get("user.name", local=True)
        lemail = gitops.git_get("user.email", local=True)
        if lname or lemail:
            print(f"repo override  : {lname or '-'} <{lemail or '-'}>")
    return 0


def cmd_remove(args, store: Store) -> int:
    store.delete(args.name)
    print(f"removed {args.name!r}")
    return 0


def cmd_test(args, store: Store) -> int:
    profile = store.get(args.name) if args.name else None
    host = profile.host if profile else args.host
    cmd = ["ssh", "-T", f"git@{host}", "-o", "StrictHostKeyChecking=accept-new"]
    key = profile.key_path() if profile else None
    if key:
        opts = ["-i", str(key), "-o", "IdentitiesOnly=yes"]
        if profile.isolate_ssh_config:
            opts = ["-F", "/dev/null"] + opts
        cmd[2:2] = opts
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    print(out or f"(no output, exit {proc.returncode})")
    return 0 if "successfully authenticated" in out.lower() else proc.returncode


EPILOG = """examples:
  # register an account (token optional; SSH remotes don't need one)
  gitp add work --user-name "Jo Dev" --email jo@company.com \\
                --ssh-key ~/.ssh/id_ed25519_work --gh-user jo-work --isolate-ssh-config

  gitp use work --local     switch this repo only  (recommended with 2+ accounts)
  gitp use work             switch globally
  gitp current              what git is using right now
  gitp test work            ssh -T github.com — prints which account answered

more: gitp help            topics on ssh keys, tokens, zsh, file locations
"""


HELP_TOPICS = {
    "ssh": """SSH keys and ~/.ssh/config
--------------------------------
`use` sets core.sshCommand to `ssh -i <key> -o IdentitiesOnly=yes`, then clears
ssh-agent and loads only that key.

Gotcha: an `IdentityFile` inside a `Host github.com` block in ~/.ssh/config is
ADDITIVE and takes precedence over `-i`. With such a block, every profile can end
up authenticating as the same account. Two ways out:

  * add --isolate-ssh-config to the profile (runs ssh with -F /dev/null, so only
    the profile's key is offered), or
  * delete the IdentityFile/IdentitiesOnly lines from that Host block and let
    gitp own the choice of key.

Always confirm with `gitp test <profile>` — it prints which account answered.""",
    "tokens": """Tokens and HTTPS remotes
--------------------------------
A token is only needed when you push over HTTPS. Over SSH remotes, the key does
the authenticating and you can leave the token unset.

  printf %s "$TOKEN" | gitp add work --user-name … --email … --token-stdin

--token-stdin keeps the token out of your shell history. On `use`, gitp sets
credential.helper=store and writes ONE line per host into ~/.git-credentials
(mode 0600), replacing any previous line for that host.

Stored in plaintext, same posture as git's own `store` helper. Don't sync
~/.config/gitp or ~/.git-credentials to a shared folder.

If you use the gh CLI, set --gh-user <account> instead and `use` will run
`gh auth switch` so gh follows the profile.""",
    "zsh": """zsh integration
--------------------------------
Completion for subcommands, profile names and flags lives in
~/.config/gitp/gitp.zsh; source it from ~/.zshrc:

  [ -f "$HOME/.config/gitp/gitp.zsh" ] && source "$HOME/.config/gitp/gitp.zsh"

It also defines gitp-prompt, which prints the identity of the repo you are in.
To show it in your prompt:

  RPROMPT='%F{242}$(gitp-prompt)%f'""",
    "files": """Where gitp keeps things
--------------------------------
  ~/.config/gitp/profiles.json   all profiles, mode 0600 (dir 0700)
  ~/.config/gitp/active          name of the last profile you switched to
  ~/.git-credentials             one line per host, only if a profile has a token

Set GITP_HOME to move the config directory (useful for testing).""",
    "scope": """Global vs --local
--------------------------------
  gitp use <profile>            writes git config --global
  gitp use <profile> --local    writes git config --local (this repo only)

With more than one account, prefer --local per repo and leave your global
identity as the fallback. `gitp current` shows the global identity, the global
sshCommand, and any repo-level override.

Fields left empty on a profile are UNSET on switch, so a profile without a key
or token can never inherit the previous profile's.""",
}


def cmd_help(args, store: Store) -> int:
    if not args.topic:
        print("Help topics — run `gitp help <topic>`:\n")
        for name, body in HELP_TOPICS.items():
            print(f"  {name:<8} {body.splitlines()[0]}")
        print("\nFor command usage: gitp --help, or gitp <command> --help")
        return 0
    if args.topic not in HELP_TOPICS:
        raise SystemExit(f"gitp: no help topic {args.topic!r} (have: {', '.join(HELP_TOPICS)})")
    print(HELP_TOPICS[args.topic])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitp",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("--version", action="version", version=f"gitp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="create or overwrite a profile")
    p_add.add_argument("name", help="profile name, e.g. work or perso")
    p_add.add_argument("--user-name", required=True, help="git user.name")
    p_add.add_argument("--email", required=True, help="git user.email")
    p_add.add_argument("--ssh-key", help="path to the private key, e.g. ~/.ssh/id_ed25519_work")
    p_add.add_argument("--login", help="account login on the host (default: user.name)")
    p_add.add_argument("--gh-user", help="gh CLI account to switch to (gh auth switch -u)")
    p_add.add_argument("--isolate-ssh-config", action="store_true",
                       help="ignore ~/.ssh/config so its IdentityFile cannot override this key")
    p_add.add_argument("--signing-key", help="user.signingkey (enables commit.gpgsign)")
    p_add.add_argument("--host", default="github.com", help="git host for the token line (default: github.com)")
    p_add.add_argument("--token", help="host token (prefer --token-stdin)")
    p_add.add_argument("--token-stdin", action="store_true", help="read the token from stdin")
    p_add.add_argument("--force", action="store_true")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", aliases=["ls"], help="list profiles")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show one profile")
    p_show.add_argument("name", help="profile to display")
    p_show.set_defaults(func=cmd_show)

    p_use = sub.add_parser("use", aliases=["switch"], help="activate a profile")
    p_use.add_argument("name", help="profile to activate")
    p_use.add_argument("--local", action="store_true", help="apply to the current repo only")
    p_use.epilog = (
        "Sets user.name/user.email, core.sshCommand, signing key, gh account and\n"
        "credential line from the profile. Fields the profile leaves empty are unset,\n"
        "so nothing carries over from the previously active profile."
    )
    p_use.formatter_class = argparse.RawDescriptionHelpFormatter
    p_use.set_defaults(func=cmd_use)

    p_cur = sub.add_parser("current", aliases=["status"], help="show what git is using now")
    p_cur.set_defaults(func=cmd_current)

    p_rm = sub.add_parser("remove", aliases=["rm"], help="delete a profile")
    p_rm.add_argument("name", help="profile to delete")
    p_rm.set_defaults(func=cmd_remove)

    p_test = sub.add_parser("test", help="ssh -T against the host to verify the key")
    p_test.add_argument("name", nargs="?", help="profile whose key to test (default: your ssh defaults)")
    p_test.add_argument("--host", default="github.com")
    p_test.set_defaults(func=cmd_test)

    p_help = sub.add_parser("help", help="longer help on a topic (ssh, tokens, zsh, files, scope)")
    p_help.add_argument("topic", nargs="?", choices=sorted(HELP_TOPICS), help="topic to explain")
    p_help.set_defaults(func=cmd_help)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args, Store())


if __name__ == "__main__":
    raise SystemExit(main())
