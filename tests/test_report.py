from types import SimpleNamespace

import pytest

from lore.bench.report import paired_bootstrap, summarize


def test_paired_bootstrap_exact_extremes_and_pairing():
    assert paired_bootstrap([1, 1, 1], [0, 0, 0]) == (100.0, [100.0, 100.0])
    assert paired_bootstrap([1, 0, 1, 0], [1, 0, 1, 0]) == (0.0, [0.0, 0.0])
    with pytest.raises(ValueError):
        paired_bootstrap([1], [])


def test_complete_report_uses_all_questions_and_partial_report_stays_partial():
    test = [SimpleNamespace(db_id="db", key=f"t{i}") for i in range(500)]
    metadata = dict(
        model="fixture",
        effort="medium",
        date="fixture",
        seed=0,
        stream_cap=50,
        dbs=["db"],
        protocols={"lore": {"checkpoints": [0.5, 1.0]}},
    )
    split = {"stream_per_db": {"db": 50}}
    rows = []
    for system, points in (
        ("floor", [0]),
        ("ceiling", [0]),
        ("lore", [0.5, 1.0]),
        ("vector", [0.5, 1.0]),
        ("flat", [1.0]),
    ):
        for checkpoint in points:
            for q in test:
                rows.append(
                    dict(
                        system=system,
                        checkpoint=checkpoint,
                        phase="test",
                        key=q.key,
                        db_id=q.db_id,
                        correct=system != "floor",
                        prompt_tokens=100,
                        block_chars=0,
                    )
                )
    summary = summarize(rows, metadata, split, test)
    assert summary["complete"] and summary["gap_closed"] == 1
    assert summary["comparisons"]["lore_minus_floor"] == dict(points=100, ci95=[100, 100], n=500)
    assert summary["systems"]["lore"][0]["questions_seen"] == 25
    partial = summarize(rows[:-1], metadata, split, test)
    assert not partial["complete"] and "lore_minus_flat" not in partial["comparisons"]
    assert partial["per_db"][0]["flat"] is None
