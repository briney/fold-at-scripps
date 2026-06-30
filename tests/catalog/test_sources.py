"""Tests for tool sources."""

from __future__ import annotations

from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord


def _record(name: str = "proteinmpnn") -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category="inverse-folding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=True,
        description="Design sequences for a backbone.",
        image_tag=f"{name}:1.0.0",
        input_schema={"type": "object", "properties": {}},
    )


def test_tool_record_validates_from_dict() -> None:
    record = ToolRecord.model_validate(
        {
            "name": "esmfold",
            "version": "1.0.0",
            "category": "structure-prediction",
            "gpu_count": 1,
            "default_timeout": 1200,
            "supports_batch": False,
            "description": "Predict structure.",
            "image_tag": "esmfold:1.0.0",
            "input_schema": {"type": "object"},
        }
    )
    assert record.name == "esmfold"
    assert record.gpu_count == 1


def test_fake_tool_source_returns_records() -> None:
    records = [_record("a"), _record("b")]
    source = FakeToolSource(records)
    assert source.fetch_tools() == records
