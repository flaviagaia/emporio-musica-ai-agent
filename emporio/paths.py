"""Bundled reference data and separately configurable local settings."""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('EMPORIO_DATA_DIR', str(Path(__file__).parent / 'data'))).expanduser()
_default_config = PROJECT_DIR if (PROJECT_DIR / 'pyproject.toml').is_file() else Path.home() / '.config' / 'mel'
CONFIG_DIR = Path(os.getenv('EMPORIO_CONFIG_DIR', str(_default_config))).expanduser()
