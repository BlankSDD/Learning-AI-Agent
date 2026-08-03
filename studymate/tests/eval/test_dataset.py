import json
from pathlib import Path


DATASET = Path(__file__).with_name("questions.jsonl")


def test_evaluation_dataset_has_required_fields():
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) >= 5
    for row in rows:
        assert row["id"]
        assert row["input"]
        assert row["intent"] in {"question", "goal", "keyword"}
        assert isinstance(row["expected_sources"], list)
        assert isinstance(row["required_terms"], list)
