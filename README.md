# gitp

Swap git profiles — identity, SSH key, signing key and host token — in one command.

## Install

```sh
pipx install git+https://github.com/Shadow88Mornach/gitp
```

Or from a clone: `pipx install .` (or `pip install -e .` for development).

## Use

```sh
# one profile per identity; the token is optional
gitp add work  --user-name "Kante Work" --email k@company.com \
               --login kante-work --ssh-key ~/.ssh/id_ed25519_work --token-stdin
gitp add perso --user-name kante --email me@perso.dev --ssh-key ~/.ssh/id_ed25519

gitp use work            # applies globally
gitp use perso --local   # applies to the current repo only
gitp current             # what git is using right now
gitp list                # '*' marks the active profile
gitp test work           # ssh -T git@github.com with that profile's key
gitp remove work

gitp help                # topics: ssh, tokens, zsh, files, scope
gitp help ssh            # the ~/.ssh/config gotcha, explained
gitp use --help          # per-command usage
```

`--token-stdin` keeps the token out of your shell history:

```sh
printf %s "$MY_TOKEN" | gitp add work --user-name … --email … --token-stdin
```

## What `use` actually changes

| Profile field | Effect |
| --- | --- |
| `user_name`, `email` | `git config user.name` / `user.email` |
| `ssh_key` | `core.sshCommand = ssh -i <key> -o IdentitiesOnly=yes`, and the key is loaded into `ssh-agent` (other identities dropped first) |
| `signing_key` | `user.signingkey` + `commit.gpgsign=true` |
| `token` + `host` | `credential.helper=store` and one line in `~/.git-credentials` for that host |

Fields left empty are **unset** on switch, so a profile without a key or token cannot inherit the previous one's.

## Where things live

- `~/.config/gitp/profiles.json` — all profiles, `0600`, directory `0700`. Override the location with `GITP_HOME`.
- `~/.config/gitp/active` — the name of the last profile you switched to.

Tokens are stored in plaintext in that file and in `~/.git-credentials`, both `0600` — the same posture as git's own `credential.helper store`. Don't put a profiles.json in a synced or shared folder.

## Tests

```sh
PYTHONPATH=src python3 -m pytest tests -q
```

## License

[MIT](LICENSE)
