from pathlib import Path

from watchbox.config import SERVER_DIR, load_settings


def _clear(monkeypatch, **overrides):
    # load_dotenv() never overrides an already-set env var, so setting every
    # relevant var here means a real server/.env can't leak into the test.
    defaults = {"EBAY_CLIENT_ID": "", "EBAY_CLIENT_SECRET": "", "REFRESH_HOURS": "6", "DB_PATH": "watchbox.db"}
    for key, value in (defaults | overrides).items():
        monkeypatch.setenv(key, value)


def test_refresh_hours_is_clamped_to_a_quarter_hour_minimum(monkeypatch):
    _clear(monkeypatch, REFRESH_HOURS="0")
    assert load_settings().refresh_hours == 0.25


def test_refresh_hours_above_minimum_is_kept(monkeypatch):
    _clear(monkeypatch, REFRESH_HOURS="6")
    assert load_settings().refresh_hours == 6.0


def test_relative_db_path_is_resolved_against_the_server_directory(monkeypatch):
    _clear(monkeypatch, DB_PATH="watchbox.db")
    assert load_settings().db_path == str(SERVER_DIR / "watchbox.db")


def test_absolute_db_path_is_kept_as_is(monkeypatch, tmp_path):
    absolute = str(tmp_path / "somewhere" / "t.db")
    _clear(monkeypatch, DB_PATH=absolute)
    assert load_settings().db_path == absolute


def test_server_dir_is_the_server_directory():
    assert (SERVER_DIR / "watchbox").is_dir()
    assert Path(SERVER_DIR).name == "server"
