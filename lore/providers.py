"""Explicit transport selection shared by the public API and teaching replays."""

import os

from lore.config import settings
from lore.llm import LLM


def create_llm(run=None, cfg=settings, cache_path=None):
    transport = os.getenv("LORE_LLM_TRANSPORT", "anthropic")
    if transport == "factory":
        from lore.factory_llm import FactoryLLM

        return FactoryLLM(run, cfg=cfg, cache_path=cache_path)
    if transport != "anthropic":
        raise ValueError("Unknown LORE_LLM_TRANSPORT")
    return LLM(run, cfg=cfg, cache_path=cache_path)
