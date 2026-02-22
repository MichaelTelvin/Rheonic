from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_arch_diagrams_generator_outputs_svg() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workspace_root = Path("/workspace")
    script_path = repo_root / "scripts" / "generate_arch_diagrams.py"
    if not script_path.exists():
        script_path = workspace_root / "scripts" / "generate_arch_diagrams.py"
        repo_root = workspace_root
    if not script_path.exists():
        pytest.skip("Architecture diagram generator script not available in this test environment")
    if shutil.which("dot") is None:
        pytest.skip("Graphviz 'dot' is not installed in this test environment")

    subprocess.run(["python", str(script_path)], check=True, cwd=repo_root)

    incident_svg = repo_root / "docs" / "architecture" / "incident_flow.svg"
    protect_svg = repo_root / "docs" / "architecture" / "protect_decision_flow.svg"
    assert incident_svg.exists()
    assert protect_svg.exists()
    assert "<svg" in incident_svg.read_text(encoding="utf-8")
    assert "<svg" in protect_svg.read_text(encoding="utf-8")
