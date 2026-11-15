import argparse
import asyncio
import csv
import io
import json
import sqlite3
from pathlib import Path

from selfgraph import relation_id

from lore.bird import db_path, description_dir, load_test, paths
from lore.config import ROOT
from lore.graphdb import GraphReader, open_graph
from lore.ids import column_id, table_id


def quote(name):
    return '"' + name.replace('"', '""') + '"'


class Schema(dict):
    def __init__(self, tables):
        super().__init__(tables)
        self.lookup = {f"{t}.{c}".lower(): f"{t}.{c}" for t in tables for c in tables[t]}
        self.table_lookup = {t.lower(): t for t in tables}
        self.by_id = {column_id(t, c): (t, c) for t in tables for c in tables[t]}

    def resolve(self, table, column):
        table = self.table_lookup.get(table.lower())
        if table:
            return next(((table, c) for c in self[table] if c.lower() == column.lower()), None)
        return None


def read_schema(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        tables = sorted(
            r[1]
            for r in conn.execute("PRAGMA table_list")
            if r[2] in ("table", "virtual") and not r[1].startswith("sqlite_")
        )
        info = {t: list(conn.execute(f"PRAGMA table_info({quote(t)})")) for t in tables}
        schema = Schema({t: {r[1]: r[2] for r in rows} for t, rows in info.items()})
        joins = set()
        for table in tables:
            for row in conn.execute(f"PRAGMA foreign_key_list({quote(table)})"):
                _, seq, target, source_col, target_col, *_ = row
                target = schema.table_lookup.get(target.lower())
                if not target:
                    continue
                if not target_col:
                    primary = sorted((r for r in info[target] if r[5]), key=lambda r: r[5])
                    target_col = primary[seq][1] if seq < len(primary) else None
                source = schema.resolve(table, source_col)
                dest = schema.resolve(target, target_col or "")
                if source and dest:
                    joins.add(tuple(sorted((column_id(*source), column_id(*dest)))))
    return schema, joins


def descriptions(directory):
    result = {}
    if not directory or not Path(directory).exists():
        return result
    for path in Path(directory).glob("*.csv"):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        for row in csv.DictReader(io.StringIO(text)):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            column = row.get("original_column_name", "")
            if column:
                result[(path.stem.lower(), column.lower())] = row
    return result


async def ingest_schema(graph, db_path, description_dir=None):
    schema, joins = await asyncio.to_thread(read_schema, db_path)
    docs = await asyncio.to_thread(descriptions, description_dir)
    entities, relations = [], []
    for table, columns in schema.items():
        tid = table_id(table)
        entities.append({"id": tid, "type": "Table", "name": table, "properties": {"table": table}})
        for column, sqltype in columns.items():
            cid = column_id(table, column)
            doc = docs.get((table.lower(), column.lower()), {})
            aliases = [column]
            display = doc.get("column_name")
            if display and display.lower() != column.lower():
                aliases.append(display)
            entities.append(
                {
                    "id": cid,
                    "type": "Column",
                    "name": f"{table}.{column}",
                    "aliases": aliases,
                    "properties": {
                        "table": table,
                        "column": column,
                        "sqltype": sqltype,
                        "description": doc.get("column_description", "")[:500],
                        "value_description": doc.get("value_description", "")[:500],
                    },
                }
            )
            relations.append({"from_entity": tid, "type": "HAS_COLUMN", "to_entity": cid})
    existing = {r.id async for r in graph.relations.iterate(type="JOINS")}
    for low, high in sorted(joins):
        if relation_id(low, "JOINS", high) not in existing:
            relations.append(
                {
                    "from_entity": low,
                    "type": "JOINS",
                    "to_entity": high,
                    "properties": {"declared": True, "wins": 0, "losses": 0},
                }
            )
    for start in range(0, len(entities), 200):
        await graph.insert.facts({"entities": entities[start : start + 200]})
    for start in range(0, len(relations), 400):
        await graph.insert.facts({"relations": relations[start : start + 400]})
    return schema


async def main(run, selected=None):
    report = {}
    slots = asyncio.Semaphore(3)

    async def one(db):
        async with slots:
            graph = await open_graph(f"{run}.lore.{db}")
            try:
                schema = await ingest_schema(graph, db_path(db), description_dir(db))
                counts = (await graph.readiness()).counts
                has_columns = len(await GraphReader(graph).all("HAS_COLUMN"))
                expected_cols = sum(map(len, schema.values()))
                assert counts["entities"] == len(schema) + expected_cols, (db, counts)
                assert has_columns == expected_cols, (db, has_columns, expected_cols)
                report[db] = {
                    "tables": len(schema),
                    "columns": expected_cols,
                    "entities": counts["entities"],
                    "has_column": has_columns,
                    "declared_joins": len(await GraphReader(graph).all("JOINS")),
                }
                print(db, json.dumps(report[db]), flush=True)
            finally:
                await graph.close()

    dbs = selected.split(",") if selected else sorted(paths()["databases"])
    await asyncio.gather(*(one(db) for db in dbs))
    for q in load_test()[:3]:
        if q.db_id not in dbs:
            continue
        graph = await open_graph(f"{run}.lore.{q.db_id}")
        try:
            seeds = await GraphReader(graph).seeds(q.question, k=10)
            print("Schema seed sanity", q.key, json.dumps(seeds), flush=True)
        finally:
            await graph.close()
    target = ROOT / "results" / run
    target.mkdir(parents=True, exist_ok=True)
    (target / "schema.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--dbs")
    args = parser.parse_args()
    asyncio.run(main(args.run, args.dbs))
