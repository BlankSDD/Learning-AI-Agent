import json
from pathlib import Path


DATASET = Path(__file__).with_name("questions.jsonl")


def test_evaluation_dataset_has_required_fields():
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) >= 15
    assert len({row["id"] for row in rows}) == len(rows)
    assert any(any("\u4e00" <= char <= "\u9fff" for char in row["input"]) for row in rows)
    assert any(any("a" <= char.lower() <= "z" for char in row["input"]) for row in rows)
    for row in rows:
        assert row["id"]
        assert row["input"]
        assert row["intent"] in {"question", "goal", "keyword"}
        assert isinstance(row["expected_sources"], list)
        assert isinstance(row["required_terms"], list)


def test_evaluation_dataset_sources_exist_in_knowledge_base():
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    knowledge_root = DATASET.parents[2] / "knowledge"

    for row in rows:
        for source in row["expected_sources"]:
            assert (knowledge_root / source).is_file(), source
