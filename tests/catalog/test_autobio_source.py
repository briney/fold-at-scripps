"""Tests for the autobio CLI tool source."""

from __future__ import annotations

import shutil

import pytest

from fold_at_scripps.catalog.autobio_source import (
    AutobioToolSource,
    parse_tool_info,
    parse_tool_names,
)

_LIST_PAYLOAD = [
    {
        "name": "ablang2",
        "category": "embedding",
        "gpu": True,
        "version": "1.0.0",
        "description": "Extract antibody embeddings using AbLang2.",
    },
    {
        "name": "proteinmpnn",
        "category": "inverse-folding",
        "gpu": True,
        "version": "1.0.0",
        "description": "Design sequences for a backbone using ProteinMPNN.",
    },
]

_INFO_PAYLOAD = {
    "name": "proteinmpnn",
    "category": "inverse-folding",
    "image_tag": "proteinmpnn:1.0.0",
    "requires_gpu": True,
    "gpu_count": 1,
    "default_timeout": 600,
    "supports_batch": True,
    "version": "1.0.0",
    "description": "Design sequences for a backbone using ProteinMPNN.",
    "input_schema": {
        "type": "object",
        "properties": {
            "structure_path": {"type": "string"},
            "num_sequences": {"type": "integer", "default": 8},
        },
        "required": ["structure_path"],
    },
}


def test_parse_tool_names() -> None:
    assert parse_tool_names(_LIST_PAYLOAD) == ["ablang2", "proteinmpnn"]


def test_parse_tool_info() -> None:
    record = parse_tool_info(_INFO_PAYLOAD)
    assert record.name == "proteinmpnn"
    assert record.version == "1.0.0"
    assert record.category == "inverse-folding"
    assert record.gpu_count == 1
    assert record.default_timeout == 600
    assert record.supports_batch is True
    assert record.image_tag == "proteinmpnn:1.0.0"
    assert record.input_schema["required"] == ["structure_path"]


@pytest.mark.skipif(shutil.which("autobio") is None, reason="autobio CLI not on PATH")
def test_autobio_source_fetches_real_tools() -> None:
    source = AutobioToolSource()
    records = source.fetch_tools()
    assert len(records) > 0
    assert all(r.name and r.version and r.input_schema is not None for r in records)
