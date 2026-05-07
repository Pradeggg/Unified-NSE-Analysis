from __future__ import annotations

import argparse
from pathlib import Path

from .config.settings import config_path, load_config
from .config.wizard import run_setup
from .data.historical import bootstrap_historical_store
from .doctor import run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-adda",
        description="Agent Adda Market Intelligence Agent installer and runtime CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup = subparsers.add_parser("setup", help="Create local Agent Adda configuration.")
    setup.add_argument("--home", type=Path, default=None, help="Agent Adda home directory.")
    setup.add_argument("--non-interactive", action="store_true", help="Run without prompts.")
    setup.add_argument(
        "--acknowledge-disclaimer",
        action="store_true",
        help="Record research-only disclaimer acknowledgement.",
    )

    doctor = subparsers.add_parser("doctor", help="Check local installation health.")
    doctor.add_argument("--home", type=Path, default=None, help="Agent Adda home directory.")

    data = subparsers.add_parser("data", help="Manage local market data.")
    data_subparsers = data.add_subparsers(dest="data_command", required=True)
    bootstrap = data_subparsers.add_parser("bootstrap", help="Bootstrap local data stores.")
    bootstrap.add_argument("--home", type=Path, default=None, help="Agent Adda home directory.")
    bootstrap.add_argument("--historical", action="store_true", help="Bootstrap EOD history.")
    bootstrap.add_argument(
        "--source",
        action="append",
        type=Path,
        default=[],
        help="CSV file or directory containing historical OHLCV files.",
    )

    subparsers.add_parser("terminal", help="Launch the NSE terminal.")
    subparsers.add_parser("agent", help="Launch the NLP market agent.")
    return parser


def _load_or_default_config(home: Path | None):
    path = config_path(home) if home else None
    return load_config(path)


def _run_setup(args: argparse.Namespace) -> int:
    config = run_setup(
        home_dir=args.home,
        non_interactive=args.non_interactive,
        acknowledge_disclaimer=args.acknowledge_disclaimer,
    )
    print(f"Config written: {config.home_dir / 'config.toml'}")
    return 0


def _run_doctor(args: argparse.Namespace) -> int:
    config = _load_or_default_config(args.home)
    result = run_doctor(config)
    for check in result.checks:
        status = "OK" if check.ok else "WARN"
        print(f"{status:4} {check.name}: {check.detail}")
    return 0 if result.ok else 1


def _run_data_bootstrap(args: argparse.Namespace) -> int:
    if not args.historical:
        raise SystemExit("Only --historical bootstrap is supported in this version.")
    config = _load_or_default_config(args.home)
    sources = args.source or [Path.cwd() / "data"]
    result = bootstrap_historical_store(config.database_path, sources)
    print(
        "Historical bootstrap complete: "
        f"{result.rows_loaded} rows loaded, "
        f"{result.rows_skipped} skipped, "
        f"{result.files_scanned} files scanned -> {result.database_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "setup":
        return _run_setup(args)
    if args.command == "doctor":
        return _run_doctor(args)
    if args.command == "data" and args.data_command == "bootstrap":
        return _run_data_bootstrap(args)
    if args.command == "terminal":
        from nse_terminal import main as terminal_main

        terminal_main()
        return 0
    if args.command == "agent":
        from nse_agent import main as agent_main

        agent_main()
        return 0
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
