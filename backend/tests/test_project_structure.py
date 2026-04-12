"""Verify the project structure and imports work correctly."""

import importlib
from pathlib import Path


def test_app_package_importable():
    """Core app package should be importable."""
    mod = importlib.import_module("backend.app")
    assert mod is not None


def test_core_package_importable():
    """Core config and database modules should be importable."""
    config_mod = importlib.import_module("backend.app.core.config")
    db_mod = importlib.import_module("backend.app.core.database")
    assert hasattr(config_mod, "settings")
    assert hasattr(db_mod, "Base")
    assert hasattr(db_mod, "get_db")


def test_main_app_importable():
    """FastAPI app and Lambda handler should be importable."""
    main_mod = importlib.import_module("backend.app.main")
    assert hasattr(main_mod, "app")
    assert hasattr(main_mod, "handler")


def test_directory_structure_exists():
    """All required directories should exist."""
    base = Path(__file__).resolve().parent.parent / "app"
    expected_dirs = ["models", "schemas", "api", "services", "core"]
    for d in expected_dirs:
        assert (base / d).is_dir(), f"Directory {d} missing"


def test_requirements_file_exists():
    """requirements.txt should exist with key dependencies."""
    req_path = Path(__file__).resolve().parent.parent / "requirements.txt"
    assert req_path.exists()
    content = req_path.read_text()
    for dep in ["fastapi", "sqlalchemy", "pydantic", "boto3",
                 "httpx", "alembic", "mangum", "openpyxl", "python-jose"]:
        assert dep in content, f"Dependency {dep} missing from requirements.txt"
