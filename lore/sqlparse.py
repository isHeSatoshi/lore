import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from lore.ids import column_id
from lore.schema_ingest import Schema


@dataclass
class Parsed:
    tables: set = field(default_factory=set)
    columns: set = field(default_factory=set)
    joins: set = field(default_factory=set)
    filter_columns: set = field(default_factory=set)

    @property
    def column_ids(self):
        return {column_id(*c) for c in self.columns}


def parse_sql(sql, schema):
    schema = schema if isinstance(schema, Schema) else Schema(schema)
    result = Parsed()
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
        try:
            tree = qualify(tree.copy(), schema=dict(schema), dialect="sqlite")
        except Exception:
            pass
        if tree is None:
            return result
        owners = {}
        scopes = list(traverse_scope(tree))
        for scope in scopes:
            for column in scope.columns:
                owners.setdefault(id(column), scope)
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    table = schema.table_lookup.get(source.name.lower())
                    if table:
                        result.tables.add(table)

        def resolve(column):
            scope = owners.get(id(column))
            if not scope:
                return None
            if column.table:
                current = scope
                while current:
                    source = next(
                        (
                            s
                            for alias, s in current.sources.items()
                            if alias.lower() == column.table.lower()
                        ),
                        None,
                    )
                    if isinstance(source, exp.Table):
                        return schema.resolve(source.name, column.name)
                    if isinstance(source, Scope):
                        return None
                    current = current.parent
                return schema.resolve(column.table, column.name)
            candidates = {
                schema.resolve(s.name, column.name)
                for s in scope.sources.values()
                if isinstance(s, exp.Table)
            }
            candidates.discard(None)
            return next(iter(candidates)) if len(candidates) == 1 else None

        for column in tree.find_all(exp.Column):
            if real := resolve(column):
                result.columns.add(real)
        for eq in tree.find_all(exp.EQ):
            if isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column):
                a, b = resolve(eq.left), resolve(eq.right)
                if a and b and a[0] != b[0]:
                    result.joins.add(tuple(sorted((a, b))))
        filters = list(tree.find_all(exp.Where, exp.Having))
        for join in tree.find_all(exp.Join):
            on = join.args.get("on")
            if on is not None and any(on.find_all(exp.Literal, exp.Null, exp.Boolean)):
                filters.append(on)
        for clause in filters:
            for column in clause.find_all(exp.Column):
                if real := resolve(column):
                    result.filter_columns.add(real)
        return result
    except Exception:
        text = sql.lower()
        for table in schema:
            if re.search(r"(?<!\w)" + re.escape(table.lower()) + r"(?!\w)", text):
                result.tables.add(table)
                for column in sorted(schema[table], key=len, reverse=True):
                    if re.search(r"(?<!\w)" + re.escape(column.lower()) + r"(?!\w)", text):
                        result.columns.add((table, column))
        return result
