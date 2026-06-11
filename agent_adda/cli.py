from __future__ import annotations

import argparse
from datetime import date
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
    strategy_lab = subparsers.add_parser("strategy-lab", help="Run the PostgreSQL portfolio strategy lab.")
    strategy_lab.add_argument("--output-dir", default="portfolio/data/nse_pg_strategy_lab/latest")
    strategy_lab.add_argument("--top-n", type=int, default=200)
    strategy_lab.add_argument("--slippage-bps", type=float, default=5.0)
    strategy_lab.add_argument("--brokerage-bps", type=float, default=3.0)

    skills = subparsers.add_parser("skills", help="Manage Agent Adda Skill Store cards.")
    skills.add_argument("--dsn", default=None, help="PostgreSQL DSN override.")
    skills_subparsers = skills.add_subparsers(dest="skills_command", required=True)
    skills_list = skills_subparsers.add_parser("list", help="List skill cards.")
    skills_list.add_argument("--status", default=None)
    skills_list.add_argument("--domain", default=None)
    skills_validate = skills_subparsers.add_parser("validate", help="Validate generated skill scenario JSONL.")
    skills_validate.add_argument("--input-jsonl", required=True)
    skills_validate.add_argument("--output-dir", default=None)
    skills_promote = skills_subparsers.add_parser("promote", help="Promote a reviewed skill card.")
    skills_promote.add_argument("skill_id")
    skills_promote.add_argument("--to", dest="to_status", default="validated", choices=("validated", "production"))
    skills_promote.add_argument("--version", type=int, default=None)
    skills_deprecate = skills_subparsers.add_parser("deprecate", help="Deprecate a skill card.")
    skills_deprecate.add_argument("skill_id")
    skills_deprecate.add_argument("--version", type=int, default=None)
    skills_deprecate.add_argument("--reason", default="")

    learning = subparsers.add_parser("learning", help="Summarize and mine Agent Adda learning logs.")
    learning.add_argument("--dsn", default=None, help="PostgreSQL DSN override.")
    learning_subparsers = learning.add_subparsers(dest="learning_command", required=True)
    learning_summarize = learning_subparsers.add_parser("summarize", help="Generate a daily learning summary.")
    learning_date = learning_summarize.add_mutually_exclusive_group(required=True)
    learning_date.add_argument("--date", default=None, help="Summary date in YYYY-MM-DD format.")
    learning_date.add_argument("--today", action="store_true", help="Summarize the current local date.")
    learning_summarize.add_argument("--write-md", action="store_true", help="Write markdown under reports/learning/daily.")
    learning_summarize.add_argument("--output-dir", default=None, help="Markdown output directory override.")
    learning_analyze = learning_subparsers.add_parser("analyze", help="Mine usage patterns from learning logs.")
    learning_analyze.add_argument("--window", default="14d", help="Date window such as 14d.")
    learning_analyze.add_argument("--end-date", default=None, help="Window end date in YYYY-MM-DD format.")
    learning_analyze.add_argument("--no-save", action="store_true", help="Do not persist mined patterns.")
    learning_propose = learning_subparsers.add_parser("propose", help="Generate proposals from mined patterns.")
    learning_propose.add_argument("--status", default="observed", help="Pattern status to convert.")
    learning_propose.add_argument("--limit", type=int, default=None, help="Maximum patterns to convert.")
    learning_validate = learning_subparsers.add_parser("validate-proposals", help="Validate generated learning proposals.")
    learning_validate.add_argument("--status", default="proposed", help="Proposal status to validate.")
    learning_proposals = learning_subparsers.add_parser("proposals", help="List learning proposals.")
    learning_proposals.add_argument("--status", default=None, help="Optional proposal status filter.")
    learning_show = learning_subparsers.add_parser("show", help="Show one learning proposal.")
    learning_show.add_argument("proposal_id", type=int)
    learning_promote = learning_subparsers.add_parser("promote", help="Promote a validated learning proposal.")
    learning_promote.add_argument("proposal_id", type=int)
    learning_promote.add_argument("--to", dest="target_status", default="validated", choices=("validated", "production"))
    learning_promote.add_argument("--approve-production", action="store_true", help="Explicitly allow production promotion.")
    learning_promote.add_argument("--output-dir", default=None, help="Backlog artifact output directory.")
    learning_reject = learning_subparsers.add_parser("reject", help="Reject a learning proposal.")
    learning_reject.add_argument("proposal_id", type=int)
    learning_reject.add_argument("--reason", default="")
    learning_audit = learning_subparsers.add_parser("audit", help="Generate a fortnightly learning audit.")
    learning_audit.add_argument("--window", default="14d")
    learning_audit.add_argument("--output-dir", default=None)
    learning_audit.add_argument("--no-save", action="store_true")
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


def _run_strategy_lab(args: argparse.Namespace) -> int:
    from portfolio.cli import main as portfolio_main

    return portfolio_main(
        [
            "strategy-lab",
            "--output-dir",
            args.output_dir,
            "--top-n",
            str(args.top_n),
            "--slippage-bps",
            str(args.slippage_bps),
            "--brokerage-bps",
            str(args.brokerage_bps),
        ]
    )


def _run_skills(args: argparse.Namespace) -> int:
    from terminal.skills.promote import deprecate_skill, list_skills, promote_skill
    from terminal.skills.scenario_validation import DEFAULT_VALIDATED_DIR, validate_skill_scenarios
    from terminal.skills.store_repo import SkillStoreRepository

    repo = SkillStoreRepository(dsn=args.dsn)
    if args.skills_command == "list":
        rows = list_skills(repository=repo, status=args.status, domain=args.domain)
        for row in rows:
            print(
                f"{row.get('id')} v{row.get('version', 1)} "
                f"{row.get('status')} {row.get('domain')} - {row.get('title', '')}"
            )
        print(f"count={len(rows)}")
        return 0
    if args.skills_command == "validate":
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_VALIDATED_DIR
        result = validate_skill_scenarios(args.input_jsonl, output_dir=output_dir)
        print(f"total={result.total}")
        for status, count in sorted(result.status_counts.items()):
            print(f"{status}={count}")
        print(f"jsonl={result.jsonl_path}")
        print(f"report={result.report_path}")
        return 0 if result.failed == 0 else 2
    if args.skills_command == "promote":
        result = promote_skill(
            args.skill_id,
            target_status=args.to_status,
            version=args.version,
            repository=repo,
        )
        print(result.message)
        return 0 if result.ok else 2
    if args.skills_command == "deprecate":
        result = deprecate_skill(
            args.skill_id,
            version=args.version,
            reason=args.reason,
            repository=repo,
        )
        print(result.message)
        return 0 if result.ok else 2
    raise SystemExit(f"Unsupported skills command: {args.skills_command}")


def _run_learning(args: argparse.Namespace) -> int:
    from terminal.learning.audit import generate_learning_audit
    from terminal.learning.daily_summary import summarize_daily_learning
    from terminal.learning.pattern_miner import analyze_learning_patterns
    from terminal.learning.proposal_generator import generate_and_save_learning_proposals
    from terminal.learning.proposal_validator import validate_and_store_learning_proposals
    from terminal.learning.promotion import (
        get_learning_proposal,
        list_learning_proposals,
        promote_learning_proposal,
        reject_learning_proposal,
    )
    from terminal.learning.repository import LearningRepository

    repo = LearningRepository(dsn=args.dsn)
    if args.learning_command == "summarize":
        summary_date = date.today().isoformat() if args.today else args.date
        result = summarize_daily_learning(
            summary_date,
            repository=repo,
            save=True,
            write_markdown=args.write_md,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        print(result.summary.markdown)
        print(f"summary_id={result.summary_id}")
        if result.markdown_path:
            print(f"markdown={result.markdown_path}")
        return 0
    if args.learning_command == "analyze":
        result = analyze_learning_patterns(
            repository=repo,
            end_date=args.end_date,
            window=args.window,
            save=not args.no_save,
        )
        print(
            "Learning patterns: "
            f"{len(result.patterns)} found, window={result.window_days}d, "
            f"{result.start_date.isoformat()}..{result.end_date.isoformat()}"
        )
        for pattern in result.patterns:
            print(
                f"{pattern.priority.upper():6} {pattern.score:3d} "
                f"{pattern.pattern_key} freq={pattern.frequency} candidate={pattern.candidate_type}"
            )
        if result.saved_pattern_ids:
            print(f"saved={len(result.saved_pattern_ids)}")
        return 0
    if args.learning_command == "propose":
        result = generate_and_save_learning_proposals(
            repository=repo,
            status=args.status,
            limit=args.limit,
        )
        print(f"Learning proposals: {len(result.proposals)} generated")
        for proposal in result.proposals:
            print(f"{proposal.proposal_type}: {proposal.title}")
        if result.saved_proposal_ids:
            print(f"saved={len(result.saved_proposal_ids)}")
        return 0
    if args.learning_command == "validate-proposals":
        result = validate_and_store_learning_proposals(repository=repo, status=args.status)
        print(f"Learning proposal validations: {len(result.results)} processed")
        for item in result.results:
            print(f"{item.status_after}: proposal_id={item.proposal_id} type={item.proposal_type}")
        if result.validation_run_ids:
            print(f"validation_runs={len(result.validation_run_ids)}")
        return 0
    if args.learning_command == "proposals":
        rows = list_learning_proposals(repository=repo, status=args.status)
        for row in rows:
            print(f"{row.get('proposal_id')} {row.get('status')} {row.get('proposal_type')} - {row.get('title')}")
        print(f"count={len(rows)}")
        return 0
    if args.learning_command == "show":
        row = get_learning_proposal(args.proposal_id, repository=repo)
        if row is None:
            print(f"proposal {args.proposal_id} not found")
            return 2
        print(f"{row.get('proposal_id')} {row.get('status')} {row.get('proposal_type')} - {row.get('title')}")
        payload = row.get("proposal_payload") or {}
        print(payload)
        return 0
    if args.learning_command == "promote":
        result = promote_learning_proposal(
            args.proposal_id,
            repository=repo,
            target_status=args.target_status,
            approve_production=args.approve_production,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        print(result.message)
        if result.artifact_path:
            print(f"artifact={result.artifact_path}")
        return 0 if result.ok else 2
    if args.learning_command == "reject":
        result = reject_learning_proposal(args.proposal_id, repository=repo, reason=args.reason)
        print(result.message)
        return 0 if result.ok else 2
    if args.learning_command == "audit":
        result = generate_learning_audit(
            repository=repo,
            window=args.window,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            save=not args.no_save,
        )
        print(f"audit_id={result.audit_id}")
        print(f"markdown={result.markdown_path}")
        print(f"html={result.html_path}")
        return 0
    raise SystemExit(f"Unsupported learning command: {args.learning_command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "setup":
        return _run_setup(args)
    if args.command == "doctor":
        return _run_doctor(args)
    if args.command == "data" and args.data_command == "bootstrap":
        return _run_data_bootstrap(args)
    if args.command == "strategy-lab":
        return _run_strategy_lab(args)
    if args.command == "skills":
        return _run_skills(args)
    if args.command == "learning":
        return _run_learning(args)
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
