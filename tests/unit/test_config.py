from __future__ import annotations

from pathlib import Path

import pytest

from jawut import config


@pytest.fixture(autouse=True)
def _isolated_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAWUT_APP_DATA_DIR", str(tmp_path / "appdata"))


def test_app_data_dir_honours_the_override(tmp_path: Path) -> None:
    assert config.app_data_dir() == tmp_path / "appdata"


def test_windows_uses_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAWUT_APP_DATA_DIR")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")
    assert config.app_data_dir().name == "Jawut"


def test_windows_falls_back_when_appdata_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAWUT_APP_DATA_DIR")
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    assert config.app_data_dir().parts[-3:] == ("AppData", "Roaming", "Jawut")


def test_macos_uses_application_support(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JAWUT_APP_DATA_DIR")
    monkeypatch.setattr("sys.platform", "darwin")
    assert config.app_data_dir().parts[-2:] == ("Application Support", "Jawut")


def test_linux_honours_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("JAWUT_APP_DATA_DIR")
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config.app_data_dir() == tmp_path / "xdg" / "jawut"


def test_missing_settings_file_yields_defaults() -> None:
    settings = config.load_settings()
    assert settings.recent_projects == []


def test_settings_round_trip() -> None:
    settings = config.load_settings()
    settings.last_export_dir = Path("/tmp/exports")
    config.save_settings(settings)
    assert config.load_settings().last_export_dir == Path("/tmp/exports")


def test_a_corrupt_settings_file_does_not_block_startup() -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert config.load_settings().recent_projects == []


def test_settings_with_the_wrong_shape_fall_back_to_defaults() -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"recent_projects": "not a list"}', encoding="utf-8")
    assert config.load_settings().recent_projects == []


def test_saving_leaves_no_temporary_files_behind() -> None:
    config.save_settings(config.load_settings())
    leftovers = list(config.app_data_dir().glob("*.tmp"))
    assert leftovers == []


def test_remember_project_puts_it_first(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()

    config.remember_project("one", first)
    settings = config.remember_project("two", second)

    assert [p.name for p in settings.recent_projects] == ["two", "one"]


def test_remembering_the_same_project_twice_does_not_duplicate_it(
    tmp_path: Path,
) -> None:
    project = tmp_path / "one"
    project.mkdir()

    config.remember_project("one", project)
    settings = config.remember_project("one", project)

    assert len(settings.recent_projects) == 1


def test_the_recent_list_is_capped(tmp_path: Path) -> None:
    for i in range(config.MAX_RECENT_PROJECTS + 5):
        project = tmp_path / f"p{i}"
        project.mkdir()
        settings = config.remember_project(f"p{i}", project)
    assert len(settings.recent_projects) == config.MAX_RECENT_PROJECTS


def test_forget_project_removes_it(tmp_path: Path) -> None:
    project = tmp_path / "one"
    project.mkdir()
    config.remember_project("one", project)

    assert config.forget_project(project).recent_projects == []


def test_existing_recent_projects_hides_missing_directories(tmp_path: Path) -> None:
    present, absent = tmp_path / "here", tmp_path / "gone"
    present.mkdir()
    absent.mkdir()
    config.remember_project("here", present)
    config.remember_project("gone", absent)
    absent.rmdir()

    assert [p.name for p in config.existing_recent_projects()] == ["here"]


def test_a_missing_project_is_kept_in_the_file_for_later(tmp_path: Path) -> None:
    absent = tmp_path / "on-a-usb-stick"
    absent.mkdir()
    config.remember_project("on-a-usb-stick", absent)
    absent.rmdir()

    assert config.existing_recent_projects() == []
    assert len(config.load_settings().recent_projects) == 1


def test_default_projects_dir_is_under_documents_when_it_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _: home))
    assert config.default_projects_dir() == home / "Documents" / "Jawut Projects"


def test_default_projects_dir_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _: home))
    assert config.default_projects_dir() == home / "Jawut Projects"
