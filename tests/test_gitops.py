from gitp import gitops
from gitp.store import Profile


def test_write_credential_replaces_only_matching_host(tmp_path, monkeypatch):
    cred = tmp_path / ".git-credentials"
    cred.write_text("https://old:tok@github.com\nhttps://me:tok@gitlab.com\n")
    monkeypatch.setattr(gitops, "CRED_FILE", cred)
    gitops.write_credential(Profile("w", "new", "n@x.dev", token="fresh"))
    lines = cred.read_text().split()
    assert lines == ["https://me:tok@gitlab.com", "https://new:fresh@github.com"]
    assert oct(cred.stat().st_mode)[-3:] == "600"


def test_token_is_url_encoded(tmp_path, monkeypatch):
    cred = tmp_path / ".git-credentials"
    monkeypatch.setattr(gitops, "CRED_FILE", cred)
    gitops.write_credential(Profile("w", "a b", "n@x.dev", token="p@ss/word"))
    assert cred.read_text().strip() == "https://a%20b:p%40ss%2Fword@github.com"


def test_no_token_writes_nothing(tmp_path, monkeypatch):
    cred = tmp_path / ".git-credentials"
    monkeypatch.setattr(gitops, "CRED_FILE", cred)
    assert gitops.write_credential(Profile("w", "a", "n@x.dev")) is None
    assert not cred.exists()
