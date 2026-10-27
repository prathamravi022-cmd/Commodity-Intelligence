"""Configuration loader. All assumptions come from config/config.yaml."""
import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def config_hash(config: dict, path: Path = CONFIG_PATH) -> str:
    """SHA-256 of the raw config file, used for reproducibility stamps."""
    if path.exists():
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    # Fallback: hash the in-memory representation.
    blob = repr(sorted(config.items())).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]
