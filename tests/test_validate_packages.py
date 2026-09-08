from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_packages import Issue, check_plugin, check_skill, parse_frontmatter


def write_skill(path: Path, description: str = "Demo skill") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: {description}\n---\n\nBody.\n",
        encoding="utf-8",
    )


def write_manifest(package: Path, homepage: str) -> None:
    (package / ".codex-plugin").mkdir(parents=True)
    (package / "assets").mkdir()
    (package / "assets" / "icon.svg").write_text("<svg></svg>\n", encoding="utf-8")
    manifest = {
        "name": package.name,
        "version": "0.0.1",
        "description": "Demo package",
        "author": {"name": "test"},
        "homepage": homepage,
        "license": "MIT",
        "skills": "./skills/",
        "interface": {
            "displayName": "Demo",
            "shortDescription": "Demo",
            "longDescription": "Demo",
            "developerName": "test",
            "category": "Productivity",
            "capabilities": ["Read"],
            "defaultPrompt": ["demo"],
            "composerIcon": "./assets/icon.svg",
            "logo": "./assets/icon.svg",
        },
    }
    (package / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def error_messages(issues: list[Issue]) -> list[str]:
    return [issue.message for issue in issues if issue.severity == "ERROR"]


def test_parse_frontmatter_accepts_yaml_block_scalars(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"
        "name: insane-search\n"
        "description: >\n"
        "  Adaptive access for blocked websites.\n"
        "  Do not trigger for simple web searches.\n"
        "---\n"
        "\nBody.\n",
        encoding="utf-8",
    )

    issues: list[Issue] = []
    frontmatter = parse_frontmatter(skill, issues)

    assert error_messages(issues) == []
    assert frontmatter["description"] == (
        "Adaptive access for blocked websites. Do not trigger for simple web searches."
    )


def test_check_skill_resolves_plugin_root_references_and_ignores_command_examples(tmp_path: Path) -> None:
    package = tmp_path / "demo-codex"
    skill_dir = package / "skills" / "demo"
    write_skill(skill_dir)
    (package / "scripts").mkdir(parents=True)
    (package / "scripts" / "tool.py").write_text("print('ok')\n", encoding="utf-8")
    (package / "shared").mkdir()
    (package / "shared" / "policy.md").write_text("Policy.\n", encoding="utf-8")
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "bootstrap.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Demo skill\n"
        "---\n"
        "\n"
        "Run `$PLUGIN_ROOT/scripts/tool.py`.\n"
        "See `$PLUGIN_ROOT/shared/policy.md §2c`.\n"
        "Optional command example: `scripts/bootstrap.sh [--install]`.\n",
        encoding="utf-8",
    )

    issues: list[Issue] = []
    check_skill(package, skill_dir, issues)

    assert error_messages(issues) == []


def test_check_skill_rejects_plugin_root_in_bash_examples(tmp_path: Path) -> None:
    package = tmp_path / "demo-codex"
    skill_dir = package / "skills" / "demo"
    write_skill(skill_dir)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Demo skill\n"
        "---\n"
        "\n"
        "```bash\n"
        'python3 "$PLUGIN_ROOT/scripts/tool.py" --check-env\n'
        "```\n",
        encoding="utf-8",
    )

    issues: list[Issue] = []
    check_skill(package, skill_dir, issues)

    assert any("$PLUGIN_ROOT" in message for message in error_messages(issues))


def test_check_skill_checks_reference_markdown_bash_examples(tmp_path: Path) -> None:
    package = tmp_path / "demo-codex"
    skill_dir = package / "skills" / "demo"
    write_skill(skill_dir)
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "eval-guide.md").write_text(
        "```bash\n"
        "python3 $PLUGIN_ROOT/skills/demo/scripts/check.py fixture\n"
        "```\n",
        encoding="utf-8",
    )

    issues: list[Issue] = []
    check_skill(package, skill_dir, issues)

    assert any("$PLUGIN_ROOT" in message for message in error_messages(issues))


def test_check_skill_rejects_claude_mcp_in_reference_examples(tmp_path: Path) -> None:
    package = tmp_path / "demo-codex"
    skill_dir = package / "skills" / "demo"
    write_skill(skill_dir)
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "mcp.md").write_text(
        "```bash\n"
        "claude mcp add playwright -- npx @playwright/mcp@latest\n"
        "```\n",
        encoding="utf-8",
    )

    issues: list[Issue] = []
    check_skill(package, skill_dir, issues)

    assert any("codex mcp" in message for message in error_messages(issues))


def test_check_skill_rejects_plugin_root_runtime_variable_claim(tmp_path: Path) -> None:
    package = tmp_path / "demo-codex"
    skill_dir = package / "skills" / "demo"
    write_skill(skill_dir)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Demo skill\n"
        "---\n"
        "\n"
        "`$PLUGIN_ROOT`는 Codex가 플러그인 실행 시 플러그인 루트로 설정하는 환경 변수다.\n",
        encoding="utf-8",
    )

    issues: list[Issue] = []
    check_skill(package, skill_dir, issues)

    assert any("runtime variable" in message for message in error_messages(issues))


def test_check_plugin_rejects_wrong_homepage(tmp_path: Path) -> None:
    package = tmp_path / "demo-codex"
    write_skill(package / "skills" / "demo")
    write_manifest(package, "https://github.com/fivetaku/gptaku_plugins/tree/main/plugins/demo-codex")

    issues: list[Issue] = []
    check_plugin(package, issues)

    assert any("homepage must be" in message for message in error_messages(issues))
