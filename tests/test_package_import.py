"""Tests for package import behavior and lazy-loaded Notion dependencies."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_import_root_package_does_not_import_notion_client() -> None:
    """Local workflow must work without loading notion_client or httpx."""
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    code = (
        "import sys\n"
        "import notion_notebook as nn\n"
        "assert nn.LocalNotebookExporter\n"
        "assert 'notion_client' not in sys.modules\n"
        "assert 'notion_notebook.notion_client' not in sys.modules\n"
    )
    subprocess.run([sys.executable, "-c", code], env=env, check=True, cwd=str(root))


def test_lazy_notebook_exporter_loads_notion_stack_when_accessed() -> None:
    """Accessing Notion symbols pulls in notion_client in a fresh interpreter."""
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    code = (
        "import sys\n"
        "import notion_notebook as nn\n"
        "assert 'notion_client' not in sys.modules\n"
        "_ = nn.NotebookExporter\n"
        "assert 'notion_client' in sys.modules\n"
    )
    subprocess.run([sys.executable, "-c", code], env=env, check=True, cwd=str(root))
