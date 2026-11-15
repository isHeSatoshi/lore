import pytest

from lore.bench.demo import select_databases


def test_demo_selection_uses_measured_gains_and_strict_size_limit():
    summary = {"per_db": [{"db_id": str(i), "floor": 50, "lore": 60 + i} for i in range(6)]}
    sizes = {str(i): 10 for i in range(6)}
    sizes["5"] = 100_000_000
    assert [row["db_id"] for row in select_databases(summary, sizes)] == ["4", "3", "2", "1"]
    summary["per_db"][0]["lore"] = None
    with pytest.raises(ValueError):
        select_databases(summary, sizes)
