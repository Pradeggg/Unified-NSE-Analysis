from __future__ import annotations

from pathlib import Path

from .settings import AppConfig, default_config, save_config


DISCLAIMER_ACK_TEXT = (
    "Agent Adda is for research and learning only. It is not investment advice, "
    "not a trading recommendation, and Agent Adda is not a SEBI registered organization."
)


def run_setup(
    *,
    home_dir: Path | None = None,
    non_interactive: bool = False,
    acknowledge_disclaimer: bool | None = None,
) -> AppConfig:
    config = default_config(home_dir)
    acknowledged = bool(acknowledge_disclaimer)
    if non_interactive and acknowledge_disclaimer is None:
        acknowledged = False
    if not non_interactive:
        print(DISCLAIMER_ACK_TEXT)
        answer = input("Acknowledge disclaimer? [y/N]: ").strip().lower()
        acknowledged = answer in {"y", "yes"}
    configured = AppConfig(
        home_dir=config.home_dir,
        data_dir=config.data_dir,
        reports_dir=config.reports_dir,
        database_path=config.database_path,
        model_mode=config.model_mode,
        openai_api_key_env=config.openai_api_key_env,
        ollama_model=config.ollama_model,
        disclaimer_acknowledged=acknowledged,
    )
    save_config(configured)
    return configured
