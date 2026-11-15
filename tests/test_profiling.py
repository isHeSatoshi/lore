import sqlite3
from types import SimpleNamespace

import pytest

from lore.ids import column_id
from lore.learn import profile_unseen_columns


@pytest.mark.asyncio
async def test_profile_budget_selects_five_unseen_columns_and_survives_partial_retry(tmp_path):
    path = tmp_path / "values.sqlite"
    names = [f"c{i:02}" for i in range(12)]
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE numbers (" + ",".join(f"{c} INT" for c in names) + ")")
        db.execute("INSERT INTO numbers VALUES (" + ",".join("1" for _ in names) + ")")
    entities = {
        column_id("numbers", c): SimpleNamespace(
            properties={"profile": "existing"} if i < 6 else {}
        )
        for i, c in enumerate(names)
    }
    entities["example:s1"] = SimpleNamespace(properties={})

    class Store:
        crashed = False

        async def get(self, key):
            return entities[key]

        async def update(self, key, properties):
            if key == column_id("numbers", "c08") and not self.crashed:
                self.crashed = True
                raise ConnectionError("Partial observation")
            entities[key].properties.update(properties)

    graph = SimpleNamespace(entities=Store())
    columns = {("numbers", c) for c in names}
    with pytest.raises(ConnectionError, match="Partial observation"):
        await profile_unseen_columns(graph, path, columns, "example:s1")
    await profile_unseen_columns(graph, path, columns, "example:s1")
    selected = entities["example:s1"].properties["_profile_columns"]
    assert selected == [["numbers", f"c{i:02}"] for i in range(6, 11)]
    assert all(entities[column_id("numbers", c)].properties.get("profile") for c in names[:11])
    assert not entities[column_id("numbers", "c11")].properties.get("profile")
