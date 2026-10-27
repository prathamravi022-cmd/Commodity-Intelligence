"""PIPE-FAIL-01: a pipeline that dies must leave evidence, not a silence.

Before this, a run that could not validate anything raised a bare ``RuntimeError``
and left nothing behind. The dashboard then showed yesterday's timestamp, which
is indistinguishable from "the pipeline has not been scheduled" — and the run
outputs written before the failure (clean rows, analytics) were newer than the
run record said.

These tests pin three things:

* missing inputs and unusable inputs are different, named failures;
* files rejected outright are counted per run instead of vanishing;
* every failing stage writes ``results/_last_failure.json`` before it re-raises,
  and the CLI turns that into a specific exit code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src import pipeline
from src.validate.clean import ValidationError, run_validation

ROOT = Path(__file__).resolve().parents[1]


def _good_frame(date: str = "05/01/2026") -> pd.DataFrame:
    return pd.DataFrame({
        "Symbol": ["GOLDM"],
        "Date": [date],
        "ExpiryDate": ["04MAY2026"],
        "Open": [7299.0],
        "High": [7310.0],
        "Low": [7295.0],
        "Close": [7300.0],
        "Volume": [1000],
        "OpenInterest": [5000],
    })


def _good_file(raw: Path, name: str = "2026-05-01.csv") -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / name
    _good_frame().to_csv(path, index=False)
    return path


def _bad_file(raw: Path, name: str = "2026-05-04.csv") -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / name
    path.write_text("nonsense,not,a,bhavcopy\n1,2,3,4\n", encoding="utf-8")
    return path


# ---- Validation classification -----------------------------------------
def test_an_empty_raw_directory_names_the_missing_input(tmp_path):
    raw, clean = tmp_path / "raw", tmp_path / "clean"
    raw.mkdir()
    with pytest.raises(ValidationError) as excinfo:
        run_validation(raw_dir=raw, clean_dir=clean)
    assert excinfo.value.reason == "no_raw_files"
    assert "ingestion has not run" in str(excinfo.value)
    # still a RuntimeError, so existing callers keep working
    assert isinstance(excinfo.value, RuntimeError)


def test_unusable_files_are_a_different_failure(tmp_path):
    raw, clean = tmp_path / "raw", tmp_path / "clean"
    _bad_file(raw)
    with pytest.raises(ValidationError) as excinfo:
        run_validation(raw_dir=raw, clean_dir=clean)
    assert excinfo.value.reason == "invalid_raw_files"
    assert "2026-05-04.csv" in str(excinfo.value)


def test_a_rejected_file_is_counted_not_dropped(tmp_path):
    raw, clean = tmp_path / "raw", tmp_path / "clean"
    _good_file(raw)
    _bad_file(raw)
    stats = run_validation(raw_dir=raw, clean_dir=clean)
    assert stats["clean_rows"] > 0
    assert stats["failed_files"] == ["2026-05-04.csv"]


def test_a_clean_run_reports_no_failed_files(tmp_path):
    raw, clean = tmp_path / "raw", tmp_path / "clean"
    _good_file(raw)
    stats = run_validation(raw_dir=raw, clean_dir=clean)
    assert stats["failed_files"] == []
    assert stats["clean_rows"] > 0


# ---- The failure record -------------------------------------------------
@pytest.fixture
def pipeline_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "results").mkdir(parents=True)
    monkeypatch.setattr(pipeline, "DATA", data)
    return data


def test_a_failing_stage_is_recorded_before_it_raises(pipeline_data, monkeypatch):
    def boom(raw_dir=None):
        raise ValidationError("nothing to validate", reason="no_raw_files")

    monkeypatch.setattr(pipeline, "run_validation", boom)
    with pytest.raises(ValidationError):
        pipeline.main()

    record = json.loads((pipeline_data / "results" / pipeline.FAILURE_NAME)
                        .read_text(encoding="utf-8"))
    assert record["stage"] == "validation"
    assert record["error_type"] == "ValidationError"
    assert record["reason"] == "no_raw_files"
    assert record["failed_utc"]
    assert "message" in record
    # no traceback, no secret material in the artifact
    assert "traceback" not in record


def test_a_later_stage_is_named_not_blamed_on_validation(pipeline_data, monkeypatch):
    monkeypatch.setattr(pipeline, "run_validation",
                        lambda raw_dir=None: {"clean_rows": 1, "rejected_rows": 0,
                                              "files": 1, "failed_files": []})

    def boom():
        raise ValueError("normalize exploded")

    monkeypatch.setattr(pipeline, "build_normalized", boom)
    with pytest.raises(ValueError):
        pipeline.main()

    record = json.loads((pipeline_data / "results" / pipeline.FAILURE_NAME)
                        .read_text(encoding="utf-8"))
    assert record["stage"] == "normalization"
    assert record["error_type"] == "ValueError"


def test_the_dashboard_can_read_what_the_pipeline_wrote(pipeline_data, monkeypatch):
    # Pins the shared filename: app.dataio reads results/_last_failure.json.
    from app import dataio

    pipeline._record_failure("validation",
                             ValidationError("no raw files", reason="no_raw_files"))
    monkeypatch.setattr(dataio, "DATA", pipeline_data)
    dataio.last_pipeline_failure.clear()
    try:
        record = dataio.last_pipeline_failure()
        assert record is not None
        assert record["stage"] == "validation"
        assert record["reason"] == "no_raw_files"
    finally:
        dataio.last_pipeline_failure.clear()


# ---- CLI exit codes -----------------------------------------------------
def test_cli_exit_codes_distinguish_the_failure_kinds(monkeypatch):
    monkeypatch.setattr(pipeline, "main", lambda **kwargs: {})
    assert pipeline.cli([]) == 0

    def validation_failure(**kwargs):
        raise ValidationError("no raw", reason="no_raw_files")

    monkeypatch.setattr(pipeline, "main", validation_failure)
    assert pipeline.cli([]) == 2

    def other_failure(**kwargs):
        raise RuntimeError("backtest exploded")

    monkeypatch.setattr(pipeline, "main", other_failure)
    assert pipeline.cli([]) == 1
