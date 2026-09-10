import json

from gitp.store import Profile, Store


def test_roundtrip_and_permissions(tmp_path):
    store = Store(tmp_path / "cfg")
    store.save(Profile("work", "Kante Work", "k@work.com", ssh_key="~/.ssh/k", token="t0ken"))
    got = store.get("work")
    assert (got.user_name, got.email, got.token) == ("Kante Work", "k@work.com", "t0ken")
    assert oct(store.path.stat().st_mode)[-3:] == "600"
    assert "name" not in json.loads(store.path.read_text())["work"]


def test_credential_login_defaults_to_user_name():
    assert Profile("p", "kante", "e@x.dev").credential_login() == "kante"
    assert Profile("p", "kante", "e@x.dev", login="k-work").credential_login() == "k-work"


def test_active_cleared_when_active_profile_removed(tmp_path):
    store = Store(tmp_path / "cfg")
    store.save(Profile("a", "A", "a@x.dev"))
    store.set_active("a")
    assert store.active() == "a"
    store.delete("a")
    assert store.active() is None
