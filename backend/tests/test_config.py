"""Regression tests for Settings' .env file resolution.

Covers a real incident: SCAN_API_KEY was visibly set in backend/.env, but
the running backend reported it as unconfigured. Root cause was
`env_file=".env"` being a relative path, resolved against the process's
current working directory at the moment `Settings()` is instantiated -
not against config.py's own location. Starting uvicorn from any directory
other than backend/ silently loaded field defaults instead (no error -
pydantic-settings just skips a missing env file).
"""

from pathlib import Path

from app.core.config import _ENV_FILE, Settings


def test_default_env_file_path_is_absolute_and_under_backend_dir() -> None:
    assert _ENV_FILE.is_absolute()
    assert _ENV_FILE.name == ".env"
    assert _ENV_FILE.parent.name == "backend"


def test_settings_loads_env_file_regardless_of_process_cwd(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / "regression.env"
    env_path.write_text("SCAN_API_KEY=regression-test-key\n", encoding="utf-8")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    # An absolute env_file path must load correctly no matter what the
    # process's cwd is at instantiation time - this is exactly the
    # property the fix relies on (an absolute _ENV_FILE instead of the
    # bare, cwd-relative ".env" string).
    settings = Settings(_env_file=env_path)

    assert settings.scan_api_key == "regression-test-key"


def test_settings_does_not_silently_use_defaults_when_cwd_lacks_env_file(
    tmp_path, monkeypatch
) -> None:
    # Sanity check for the *old*, buggy behavior this test file guards
    # against: a bare relative ".env" resolved against an unrelated cwd
    # finds nothing and falls back to the field default - proving the
    # failure mode was real, not hypothetical.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    settings_with_relative_path = Settings(_env_file=Path(".env"))

    assert settings_with_relative_path.scan_api_key == ""
