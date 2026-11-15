"""Bound client connections without changing graph queries or learning."""

from functools import partial

GRAPH_POOL_SIZE = 4


def configure_graph_pool():
    from selfgraph import HydraDBStore

    from lore import graphdb

    # SelfGraph forwards this public constructor option to the Neo4j driver.
    # Each namespace has a driver; the default of 100 multiplies across them.
    graphdb.HydraDBStore = partial(
        HydraDBStore, max_connection_pool_size=GRAPH_POOL_SIZE
    )
    return GRAPH_POOL_SIZE
