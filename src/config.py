"""实验配置加载"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    # Only read the project's own .env. Existing process variables take priority.
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    cfg_path = Path(path) if path else ROOT / "configs" / "default.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # 环境变量覆盖（API Key 不落仓库）
    cfg["llm"]["api_key"] = os.getenv("LLM_API_KEY", cfg["llm"].get("api_key", ""))
    cfg["llm"]["base_url"] = os.getenv("LLM_BASE_URL", cfg["llm"]["base_url"])
    cfg["llm"]["model"] = os.getenv("LLM_MODEL", cfg["llm"]["model"])
    if os.getenv("LLM_TEMPERATURE"):
        cfg["llm"]["temperature"] = float(os.environ["LLM_TEMPERATURE"])
    return cfg
