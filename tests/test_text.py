import json

import pytest
from pydantic import ValidationError

from lore.api import Ask
from lore.text import entity_label, trace_summary


def test_metadata_handles_multiline_sql_without_changing_literal_contents():
    sql = "SELECT 'two  spaces', 'a\nb'\nFROM orders"
    assert json.loads('"' + trace_summary(sql) + '"') == sql
    assert entity_label(" How much\nrevenue?\t", 300) == "How much revenue?"
    with pytest.raises(ValidationError):
        Ask(db="fixture", question="unpaired\ud800")
