import json
from pathlib import Path


def test_frontend_quality_commands_are_fixed_in_package_manifest() -> None:
    package = json.loads(Path("apps/web/package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]

    assert scripts["test"] == "vitest run"
    assert scripts["typecheck"] == "tsc --noEmit"
    assert "vitest run" in scripts["test:mobile"]
    assert "vitest run" in scripts["test:a11y"]
    assert "prettier --check" in scripts["format:check"]
    assert "test" in scripts["quality"]
    assert "typecheck" in scripts["quality"]
    assert "test:mobile" in scripts["quality"]
    assert "test:a11y" in scripts["quality"]
