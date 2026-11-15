import hashlib
import re

from selfgraph import entity_id


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "x"


def short(value):
    return hashlib.sha1(value.encode()).hexdigest()[:6]


def table_id(table):
    return f"table:{slug(table)}-{short(table)}"


def column_id(table, column):
    return f"column:{slug(table)}.{slug(column)}-{short(table + '.' + column)}"


def example_id(key):
    return f"example:{slug(key)}"


def term_id(name):
    return entity_id("Term", name.lower().strip())
