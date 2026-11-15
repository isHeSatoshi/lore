from copy import deepcopy

import pytest

from deploy.hf.check_release import graph_digest


def test_graph_digest_compares_records_not_response_order():
    graph = {
        "nodes": [{"id": "b"}, {"id": "a"}],
        "edges": [{"id": "x", "wins": 1}, {"id": "y", "wins": 2}],
    }
    reordered = {key: list(reversed(value)) for key, value in graph.items()}
    assert graph_digest(graph) == graph_digest(reordered)
    changed = deepcopy(graph)
    changed["edges"][0]["wins"] = 2
    assert graph_digest(graph) != graph_digest(changed)


def test_graph_digest_preserves_duplicate_record_counts():
    graph = {"nodes": [{"id": "a"}], "edges": [{"id": "x"}]}
    duplicated = deepcopy(graph)
    duplicated["edges"].append({"id": "x"})
    assert graph_digest(graph) != graph_digest(duplicated)


def test_graph_digest_rejects_empty_trained_graph():
    with pytest.raises(AssertionError, match="empty trained graph"):
        graph_digest({"nodes": [], "edges": []})
