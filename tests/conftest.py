"""Pytest configuration and fixtures."""

import pytest
import sys
from pathlib import Path

# Add src to Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_pdf_path():
    """Path to a sample PDF for testing."""
    return project_root / "data" / "incoming" / "Itau_2024-10.pdf"


@pytest.fixture
def golden_dir():
    """Path to golden files directory."""
    return project_root / "data" / "golden"


@pytest.fixture
def output_dir(tmp_path):
    """Temporary output directory for tests."""
    return tmp_path / "output"
