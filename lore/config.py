import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.getenv("LORE_ROOT", str(Path(__file__).resolve().parents[1]))).resolve()
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv("LORE_LLM_BASE_URL", "https://api.minimax.io/anthropic")
    api_key: str = os.getenv("LORE_LLM_API_KEY", "")
    model: str = os.getenv("LORE_LLM_MODEL", "MiniMax-M3.1-Flash")
    effort: str = os.getenv("LORE_LLM_EFFORT", "")
    max_tokens: int = int(os.getenv("LORE_LLM_MAX_TOKENS", "8192"))
    concurrency: int = int(os.getenv("LORE_LLM_CONCURRENCY", "8"))
    min_interval_s: float = float(os.getenv("LORE_LLM_MIN_INTERVAL_S", "0"))
    hydra_token: str = os.getenv("HYDRA_TOKEN", "")
    bolt_uri: str = os.getenv("HYDRA_BOLT_URI", "bolt://127.0.0.1:17687")
    admin_url: str = os.getenv("HYDRA_ADMIN_URL", "http://127.0.0.1:19091")
    http_url: str = os.getenv("HYDRA_HTTP_URL", "http://127.0.0.1:18443")
    data_dir: Path = (ROOT / os.getenv("LORE_DATA_DIR", "./data")).resolve()
    run: str = os.getenv("LORE_RUN", "r1")

    @property
    def bird_dir(self):
        return self.data_dir / "bird"


settings = Settings()
