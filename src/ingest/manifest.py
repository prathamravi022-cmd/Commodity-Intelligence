"""Compute and record SHA-256 checksums of raw files (DATA-005, security doc 6.1)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def update_manifest(data_dir: Path, files: list[Path], extra: dict | None = None) -> Path:
    """Record file -> {sha256, download_time, row_count} in manifest.json."""
    manifest_path = data_dir / MANIFEST_NAME
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
    now = datetime.now(timezone.utc).isoformat()
    for f in files:
        rows = 0
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                rows = max(0, sum(1 for _ in fh) - 1)
        except OSError:
            rows = 0
        manifest[f.name] = {
            "sha256": sha256(f),
            "download_time": now,
            "row_count": rows,
        }
    if extra:
        manifest["_meta"] = {**manifest.get("_meta", {}), **extra}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path
