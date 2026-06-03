from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio.engine.strategy_library import get_strategy_spec


def publish_daily_paper_portfolio(
    *,
    output_dir: Path,
    summary: dict[str, Any],
    leaderboard: pd.DataFrame,
    features: pd.DataFrame,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Publish current paper portfolio artifacts for the top ranked strategy."""

    paper_dir = output_dir / "paper"
    reports_dir = output_dir / "reports"
    paper_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    selected = _selected_strategy(leaderboard)
    selected_strategy_id = str(selected.get("strategy_id") or "n/a")
    state_path = output_dir / "runs" / selected_strategy_id / "state" / "replay_state.json"
    state = _read_json(state_path) if state_path.exists() else _empty_state(summary)
    spec = _strategy_spec(selected_strategy_id)
    marks = _latest_feature_marks(features)

    positions = _position_rows(state.get("positions", []), marks, spec)
    daily_pnl = _daily_pnl_rows(state.get("nav_history", []))
    trades = _trade_rows(
        state.get("fills", []),
        orders=state.get("orders", []),
        feature_marks=_feature_marks_by_date(features),
        spec=spec,
    )
    as_of = str(summary.get("end_date") or summary.get("latest_eod_date") or "n/a")
    next_orders = _next_order_rows(
        state.get("orders", []),
        positions=positions,
        marks=marks,
        spec=spec,
        as_of=as_of,
    )

    positions_path = paper_dir / "positions.csv"
    daily_pnl_path = paper_dir / "daily_pnl.csv"
    trades_path = paper_dir / "trades.csv"
    next_orders_path = paper_dir / "next_orders.csv"
    actions_path = paper_dir / "agent_actions.jsonl"
    state_out_path = paper_dir / "portfolio_state.json"
    report_path = reports_dir / "paper_portfolio_report.md"

    pd.DataFrame(positions).to_csv(positions_path, index=False)
    pd.DataFrame(daily_pnl).to_csv(daily_pnl_path, index=False)
    pd.DataFrame(trades).to_csv(trades_path, index=False)
    pd.DataFrame(next_orders).to_csv(next_orders_path, index=False)

    latest_pnl = daily_pnl[-1] if daily_pnl else {}
    portfolio_state = {
        "run_id": summary.get("run_id"),
        "as_of": as_of,
        "selected_strategy_id": selected_strategy_id,
        "selected_strategy_name": selected.get("name") or spec.get("name") or selected_strategy_id,
        "selection_reason": "Top active strategy by strategy-lab rank_score after costs and drawdown checks.",
        "source_run_state": str(state_path),
        "account": state.get("account", {}),
        "strategy_metrics": dict(selected),
        "latest_snapshot": latest_pnl,
        "open_positions": len(positions),
        "total_market_value": _round(sum(_number(row.get("market_value")) or 0.0 for row in positions)),
        "total_unrealized_pnl": _round(sum(_number(row.get("unrealized_pnl")) or 0.0 for row in positions)),
        "today_pnl": latest_pnl.get("daily_pnl", 0.0),
        "today_return_pct": latest_pnl.get("daily_return_pct", 0.0),
        "positions": positions,
        "artifacts": {
            "state": str(state_out_path),
            "positions": str(positions_path),
            "daily_pnl": str(daily_pnl_path),
            "trades": str(trades_path),
            "next_orders": str(next_orders_path),
            "agent_actions": str(actions_path),
            "report": str(report_path),
        },
    }
    _write_json(state_out_path, portfolio_state)

    actions = _agent_actions(portfolio_state, selected, trades)
    actions_path.write_text(
        "\n".join(json.dumps(_json_safe(row), allow_nan=False, sort_keys=True) for row in actions) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_paper_report(portfolio_state, positions, daily_pnl, trades, next_orders), encoding="utf-8")
    database = (
        persist_paper_portfolio_to_postgres(
            dsn=dsn,
            portfolio_state=portfolio_state,
            positions=positions,
            daily_pnl=daily_pnl,
            trades=trades,
            next_orders=next_orders,
            actions=actions,
        )
        if dsn
        else {"success": False, "reason": "database persistence disabled"}
    )
    portfolio_state["database"] = database
    _write_json(state_out_path, portfolio_state)

    return {
        "selected_strategy_id": selected_strategy_id,
        "selected_strategy_name": portfolio_state["selected_strategy_name"],
        "as_of": as_of,
        "open_positions": portfolio_state["open_positions"],
        "today_pnl": portfolio_state["today_pnl"],
        "today_return_pct": portfolio_state["today_return_pct"],
        "total_unrealized_pnl": portfolio_state["total_unrealized_pnl"],
        "artifacts": portfolio_state["artifacts"],
        "next_orders": len(next_orders),
        "database": database,
    }


def persist_paper_portfolio_to_postgres(
    *,
    dsn: str,
    portfolio_state: dict[str, Any],
    positions: list[dict[str, Any]],
    daily_pnl: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    next_orders: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist the daily paper portfolio package into dedicated PostgreSQL tables."""

    run_id = str(portfolio_state.get("run_id") or "")
    if not run_id:
        return {"success": False, "error": "missing run_id"}
    try:
        with _connect_postgres(dsn) as conn:
            with conn.cursor() as cur:
                _ensure_paper_tables(cur)
                _delete_existing_paper_run_rows(cur, run_id)
                _upsert_paper_run(cur, portfolio_state)
                for row in positions:
                    _upsert_paper_position(cur, run_id, portfolio_state.get("as_of"), row)
                for row in daily_pnl:
                    _upsert_paper_daily_pnl(cur, run_id, row)
                for row in trades:
                    _upsert_paper_transaction(cur, run_id, row)
                for row in next_orders or []:
                    _upsert_paper_next_order(cur, run_id, row)
                for index, row in enumerate(actions, start=1):
                    _upsert_paper_agent_action(cur, run_id, index, row)
        return {
            "success": True,
            "schema": "portfolio",
            "tables": [
                "portfolio.paper_runs",
                "portfolio.paper_positions",
                "portfolio.paper_daily_pnl",
                "portfolio.paper_transactions",
                "portfolio.paper_next_orders",
                "portfolio.paper_agent_actions",
            ],
            "run_id": run_id,
            "positions": len(positions),
            "daily_pnl": len(daily_pnl),
            "transactions": len(trades),
            "next_orders": len(next_orders or []),
            "agent_actions": len(actions),
        }
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def _connect_postgres(dsn: str):
    import psycopg2

    return psycopg2.connect(dsn)


def _json_param(value: Any) -> Any:
    from psycopg2.extras import Json

    return Json(_json_safe(value))


def _date_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text and text.lower() != "n/a" else None


def _ensure_paper_tables(cur: Any) -> None:
    cur.execute("CREATE SCHEMA IF NOT EXISTS portfolio")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio.paper_runs (
            run_id text PRIMARY KEY,
            as_of date,
            selected_strategy_id text,
            selected_strategy_name text,
            source_run_state text,
            state_json jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio.paper_positions (
            run_id text NOT NULL,
            as_of date NOT NULL,
            symbol text NOT NULL,
            quantity numeric,
            avg_price numeric,
            avg_cost numeric,
            current_price numeric,
            market_value numeric,
            unrealized_pnl numeric,
            unrealized_pct numeric,
            stage text,
            rsi_14 numeric,
            relative_strength numeric,
            stop_price numeric,
            target_price numeric,
            reward_risk numeric,
            exit_trigger text,
            raw_json jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, as_of, symbol)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio.paper_daily_pnl (
            run_id text NOT NULL,
            pnl_date date NOT NULL,
            cash numeric,
            market_value numeric,
            nav numeric,
            daily_pnl numeric,
            daily_return_pct numeric,
            cumulative_return_pct numeric,
            drawdown_pct numeric,
            open_positions integer,
            raw_json jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, pnl_date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio.paper_transactions (
            run_id text NOT NULL,
            fill_id text NOT NULL,
            trade_date date,
            strategy_id text,
            symbol text,
            side text,
            trade_intent text,
            signal_date date,
            signal_reason text,
            entry_date date,
            quantity numeric,
            price numeric,
            entry_price numeric,
            stop_price numeric,
            target_price numeric,
            risk_amount numeric,
            realized_pnl numeric,
            r_multiple numeric,
            holding_period_days integer,
            notional numeric,
            fees numeric,
            slippage numeric,
            cash_effect numeric,
            order_id text,
            raw_json jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, fill_id)
        )
        """
    )
    for column, definition in (
        ("trade_intent", "text"),
        ("signal_date", "date"),
        ("signal_reason", "text"),
        ("entry_date", "date"),
        ("entry_price", "numeric"),
        ("stop_price", "numeric"),
        ("target_price", "numeric"),
        ("risk_amount", "numeric"),
        ("realized_pnl", "numeric"),
        ("r_multiple", "numeric"),
        ("holding_period_days", "integer"),
    ):
        cur.execute(f"ALTER TABLE portfolio.paper_transactions ADD COLUMN IF NOT EXISTS {column} {definition}")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio.paper_next_orders (
            run_id text NOT NULL,
            order_id text NOT NULL,
            order_date date,
            strategy_id text,
            symbol text,
            side text,
            trade_intent text,
            quantity numeric,
            order_type text,
            signal_reason text,
            reference_price numeric,
            stop_price numeric,
            target_price numeric,
            risk_per_share numeric,
            estimated_risk numeric,
            estimated_notional numeric,
            raw_json jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, order_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio.paper_agent_actions (
            run_id text NOT NULL,
            action_index integer NOT NULL,
            action_date date,
            agent text,
            action text,
            strategy_id text,
            reason text,
            payload jsonb,
            raw_json jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, action_index)
        )
        """
    )


def _delete_existing_paper_run_rows(cur: Any, run_id: str) -> None:
    for table in (
        "portfolio.paper_positions",
        "portfolio.paper_daily_pnl",
        "portfolio.paper_transactions",
        "portfolio.paper_next_orders",
        "portfolio.paper_agent_actions",
    ):
        cur.execute(f"DELETE FROM {table} WHERE run_id = %s", (run_id,))


def _upsert_paper_run(cur: Any, state: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO portfolio.paper_runs (
            run_id, as_of, selected_strategy_id, selected_strategy_name, source_run_state, state_json
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id) DO UPDATE SET
            as_of = EXCLUDED.as_of,
            selected_strategy_id = EXCLUDED.selected_strategy_id,
            selected_strategy_name = EXCLUDED.selected_strategy_name,
            source_run_state = EXCLUDED.source_run_state,
            state_json = EXCLUDED.state_json,
            updated_at = now()
        """,
        (
            state.get("run_id"),
            _date_or_none(state.get("as_of")),
            state.get("selected_strategy_id"),
            state.get("selected_strategy_name"),
            state.get("source_run_state"),
            _json_param(state),
        ),
    )


def _upsert_paper_position(cur: Any, run_id: str, as_of: Any, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO portfolio.paper_positions (
            run_id, as_of, symbol, quantity, avg_price, avg_cost, current_price, market_value,
            unrealized_pnl, unrealized_pct, stage, rsi_14, relative_strength, stop_price,
            target_price, reward_risk, exit_trigger, raw_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, as_of, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            avg_price = EXCLUDED.avg_price,
            avg_cost = EXCLUDED.avg_cost,
            current_price = EXCLUDED.current_price,
            market_value = EXCLUDED.market_value,
            unrealized_pnl = EXCLUDED.unrealized_pnl,
            unrealized_pct = EXCLUDED.unrealized_pct,
            stage = EXCLUDED.stage,
            rsi_14 = EXCLUDED.rsi_14,
            relative_strength = EXCLUDED.relative_strength,
            stop_price = EXCLUDED.stop_price,
            target_price = EXCLUDED.target_price,
            reward_risk = EXCLUDED.reward_risk,
            exit_trigger = EXCLUDED.exit_trigger,
            raw_json = EXCLUDED.raw_json,
            updated_at = now()
        """,
        (
            run_id,
            _date_or_none(as_of),
            row.get("symbol"),
            _number(row.get("quantity")),
            _number(row.get("avg_price")),
            _number(row.get("avg_cost")),
            _number(row.get("current_price")),
            _number(row.get("market_value")),
            _number(row.get("unrealized_pnl")),
            _number(row.get("unrealized_pct")),
            row.get("stage"),
            _number(row.get("rsi_14")),
            _number(row.get("relative_strength")),
            _number(row.get("stop_price")),
            _number(row.get("target_price")),
            _number(row.get("reward_risk")),
            row.get("exit_trigger"),
            _json_param(row),
        ),
    )


def _upsert_paper_daily_pnl(cur: Any, run_id: str, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO portfolio.paper_daily_pnl (
            run_id, pnl_date, cash, market_value, nav, daily_pnl, daily_return_pct,
            cumulative_return_pct, drawdown_pct, open_positions, raw_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, pnl_date) DO UPDATE SET
            cash = EXCLUDED.cash,
            market_value = EXCLUDED.market_value,
            nav = EXCLUDED.nav,
            daily_pnl = EXCLUDED.daily_pnl,
            daily_return_pct = EXCLUDED.daily_return_pct,
            cumulative_return_pct = EXCLUDED.cumulative_return_pct,
            drawdown_pct = EXCLUDED.drawdown_pct,
            open_positions = EXCLUDED.open_positions,
            raw_json = EXCLUDED.raw_json,
            updated_at = now()
        """,
        (
            run_id,
            _date_or_none(row.get("date")),
            _number(row.get("cash")),
            _number(row.get("market_value")),
            _number(row.get("nav")),
            _number(row.get("daily_pnl")),
            _number(row.get("daily_return_pct")),
            _number(row.get("cumulative_return_pct")),
            _number(row.get("drawdown_pct")),
            int(_number(row.get("open_positions")) or 0),
            _json_param(row),
        ),
    )


def _upsert_paper_transaction(cur: Any, run_id: str, row: dict[str, Any]) -> None:
    fill_id = str(row.get("fill_id") or row.get("order_id") or f"{row.get('date')}-{row.get('symbol')}-{row.get('side')}")
    cur.execute(
        """
        INSERT INTO portfolio.paper_transactions (
            run_id, fill_id, trade_date, strategy_id, symbol, side, trade_intent,
            signal_date, signal_reason, entry_date, quantity, price, entry_price,
            stop_price, target_price, risk_amount, realized_pnl, r_multiple,
            holding_period_days, notional, fees, slippage, cash_effect, order_id, raw_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, fill_id) DO UPDATE SET
            trade_date = EXCLUDED.trade_date,
            strategy_id = EXCLUDED.strategy_id,
            symbol = EXCLUDED.symbol,
            side = EXCLUDED.side,
            trade_intent = EXCLUDED.trade_intent,
            signal_date = EXCLUDED.signal_date,
            signal_reason = EXCLUDED.signal_reason,
            entry_date = EXCLUDED.entry_date,
            quantity = EXCLUDED.quantity,
            price = EXCLUDED.price,
            entry_price = EXCLUDED.entry_price,
            stop_price = EXCLUDED.stop_price,
            target_price = EXCLUDED.target_price,
            risk_amount = EXCLUDED.risk_amount,
            realized_pnl = EXCLUDED.realized_pnl,
            r_multiple = EXCLUDED.r_multiple,
            holding_period_days = EXCLUDED.holding_period_days,
            notional = EXCLUDED.notional,
            fees = EXCLUDED.fees,
            slippage = EXCLUDED.slippage,
            cash_effect = EXCLUDED.cash_effect,
            order_id = EXCLUDED.order_id,
            raw_json = EXCLUDED.raw_json,
            updated_at = now()
        """,
        (
            run_id,
            fill_id,
            _date_or_none(row.get("date")),
            row.get("strategy_id"),
            row.get("symbol"),
            row.get("side"),
            row.get("trade_intent"),
            _date_or_none(row.get("signal_date")),
            row.get("signal_reason"),
            _date_or_none(row.get("entry_date")),
            _number(row.get("quantity")),
            _number(row.get("price")),
            _number(row.get("entry_price")),
            _number(row.get("stop_price")),
            _number(row.get("target_price")),
            _number(row.get("risk_amount")),
            _number(row.get("realized_pnl")),
            _number(row.get("r_multiple")),
            int(_number(row.get("holding_period_days")) or 0) if row.get("holding_period_days") not in (None, "") else None,
            _number(row.get("notional")),
            _number(row.get("fees")),
            _number(row.get("slippage")),
            _number(row.get("cash_effect")),
            row.get("order_id"),
            _json_param(row),
        ),
    )


def _upsert_paper_next_order(cur: Any, run_id: str, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO portfolio.paper_next_orders (
            run_id, order_id, order_date, strategy_id, symbol, side, trade_intent,
            quantity, order_type, signal_reason, reference_price, stop_price,
            target_price, risk_per_share, estimated_risk, estimated_notional, raw_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, order_id) DO UPDATE SET
            order_date = EXCLUDED.order_date,
            strategy_id = EXCLUDED.strategy_id,
            symbol = EXCLUDED.symbol,
            side = EXCLUDED.side,
            trade_intent = EXCLUDED.trade_intent,
            quantity = EXCLUDED.quantity,
            order_type = EXCLUDED.order_type,
            signal_reason = EXCLUDED.signal_reason,
            reference_price = EXCLUDED.reference_price,
            stop_price = EXCLUDED.stop_price,
            target_price = EXCLUDED.target_price,
            risk_per_share = EXCLUDED.risk_per_share,
            estimated_risk = EXCLUDED.estimated_risk,
            estimated_notional = EXCLUDED.estimated_notional,
            raw_json = EXCLUDED.raw_json,
            updated_at = now()
        """,
        (
            run_id,
            row.get("order_id"),
            _date_or_none(row.get("date")),
            row.get("strategy_id"),
            row.get("symbol"),
            row.get("side"),
            row.get("trade_intent"),
            _number(row.get("quantity")),
            row.get("order_type"),
            row.get("signal_reason"),
            _number(row.get("reference_price")),
            _number(row.get("stop_price")),
            _number(row.get("target_price")),
            _number(row.get("risk_per_share")),
            _number(row.get("estimated_risk")),
            _number(row.get("estimated_notional")),
            _json_param(row),
        ),
    )


def _upsert_paper_agent_action(cur: Any, run_id: str, index: int, row: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO portfolio.paper_agent_actions (
            run_id, action_index, action_date, agent, action, strategy_id, reason, payload, raw_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, action_index) DO UPDATE SET
            action_date = EXCLUDED.action_date,
            agent = EXCLUDED.agent,
            action = EXCLUDED.action,
            strategy_id = EXCLUDED.strategy_id,
            reason = EXCLUDED.reason,
            payload = EXCLUDED.payload,
            raw_json = EXCLUDED.raw_json,
            updated_at = now()
        """,
        (
            run_id,
            index,
            _date_or_none(row.get("timestamp")),
            row.get("agent"),
            row.get("action"),
            row.get("strategy_id"),
            row.get("reason"),
            _json_param(row.get("payload") or {}),
            _json_param(row),
        ),
    )


def _selected_strategy(leaderboard: pd.DataFrame) -> dict[str, Any]:
    if leaderboard.empty:
        return {"strategy_id": "n/a", "name": "n/a"}
    return dict(leaderboard.iloc[0].to_dict())


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), allow_nan=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _empty_state(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": summary.get("run_id"),
        "account": {"initial_capital": summary.get("initial_capital"), "cash": summary.get("initial_capital")},
        "positions": [],
        "fills": [],
        "nav_history": [],
    }


def _strategy_spec(strategy_id: str) -> dict[str, Any]:
    try:
        return get_strategy_spec(strategy_id)
    except KeyError:
        return {"strategy_id": strategy_id, "name": strategy_id, "risk": {"initial_stop": {"multiple": 2.0}}}


def _latest_feature_marks(features: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if features.empty or "symbol" not in features.columns:
        return {}
    frame = features.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "symbol"]).sort_values(["symbol", "date"])
    latest = frame.groupby("symbol", as_index=False).tail(1)
    marks: dict[str, dict[str, Any]] = {}
    for _, row in latest.iterrows():
        symbol = str(row["symbol"]).upper()
        marks[symbol] = {
            "date": str(pd.to_datetime(row["date"]).date()),
            "close": _number(row.get("close")),
            "atr_14": _number(row.get("atr_14")),
            "stage": row.get("stage"),
            "rsi_14": _number(row.get("rsi_14")),
            "relative_strength": _number(row.get("relative_strength")),
            "sma_20": _number(row.get("sma_20")),
            "sma_50": _number(row.get("sma_50")),
        }
    return marks


def _feature_marks_by_date(features: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    if features.empty or not {"date", "symbol"}.issubset(features.columns):
        return {}
    frame = features.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "symbol"])
    marks: dict[tuple[str, str], dict[str, Any]] = {}
    for _, row in frame.iterrows():
        date = str(pd.to_datetime(row["date"]).date())
        symbol = str(row["symbol"]).upper()
        marks[(date, symbol)] = {
            "close": _number(row.get("close")),
            "atr_14": _number(row.get("atr_14")),
            "stage": row.get("stage"),
            "rsi_14": _number(row.get("rsi_14")),
            "relative_strength": _number(row.get("relative_strength")),
        }
    return marks


def _position_rows(positions: list[Any], marks: dict[str, dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stop_multiple = _number(((spec.get("risk") or {}).get("initial_stop") or {}).get("multiple")) or 2.0
    for position in positions:
        symbol = str(_field(position, "symbol") or "").upper()
        quantity = int(_number(_field(position, "quantity")) or 0)
        if not symbol or quantity <= 0:
            continue
        mark = marks.get(symbol, {})
        avg_cost = _number(_field(position, "avg_cost")) or _number(_field(position, "avg_price")) or 0.0
        avg_price = _number(_field(position, "avg_price")) or avg_cost
        current_price = _number(mark.get("close")) or avg_price
        atr = _number(mark.get("atr_14"))
        market_value = quantity * current_price
        cost_value = quantity * avg_cost
        unrealized_pnl = market_value - cost_value
        stop_price = max(0.0, current_price - stop_multiple * atr) if atr and atr > 0 else None
        risk_per_share = current_price - stop_price if stop_price is not None else None
        target_price = current_price + (2.0 * risk_per_share) if risk_per_share is not None else None
        rows.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "avg_price": _round(avg_price),
                "avg_cost": _round(avg_cost),
                "current_price": _round(current_price),
                "market_value": _round(market_value),
                "unrealized_pnl": _round(unrealized_pnl),
                "unrealized_pct": _round((unrealized_pnl / cost_value) * 100.0 if cost_value else 0.0),
                "stage": mark.get("stage") or "n/a",
                "rsi_14": _round(mark.get("rsi_14")),
                "relative_strength": _round(mark.get("relative_strength")),
                "stop_price": _round(stop_price),
                "target_price": _round(target_price),
                "reward_risk": 2.0 if stop_price is not None else None,
                "exit_trigger": _exit_trigger(stop_price),
                "strategy_ids": _format_strategy_ids(_field(position, "strategy_ids")),
            }
        )
    return sorted(rows, key=lambda row: str(row["symbol"]))


def _daily_pnl_rows(nav_history: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_nav: float | None = None
    peak_nav = 0.0
    starting_nav: float | None = None
    for snapshot in nav_history:
        nav = _number(_field(snapshot, "nav", _field(snapshot, "equity"))) or 0.0
        if starting_nav is None and nav > 0:
            starting_nav = nav
        daily_pnl = 0.0 if previous_nav is None else nav - previous_nav
        daily_return = 0.0 if previous_nav in {None, 0.0} else daily_pnl / previous_nav * 100.0
        peak_nav = max(peak_nav, nav)
        drawdown = 0.0 if peak_nav <= 0 else (nav / peak_nav - 1.0) * 100.0
        cumulative_return = 0.0 if not starting_nav else (nav / starting_nav - 1.0) * 100.0
        rows.append(
            {
                "date": str(_field(snapshot, "timestamp", "n/a")),
                "cash": _round(_field(snapshot, "cash")),
                "market_value": _round(_field(snapshot, "market_value")),
                "nav": _round(nav),
                "daily_pnl": _round(daily_pnl),
                "daily_return_pct": _round(daily_return),
                "cumulative_return_pct": _round(cumulative_return),
                "drawdown_pct": _round(drawdown),
                "open_positions": int(_number(_field(snapshot, "open_positions")) or 0),
            }
        )
        previous_nav = nav
    return rows


def _next_order_rows(
    orders: list[Any],
    *,
    positions: list[dict[str, Any]],
    marks: dict[str, dict[str, Any]],
    spec: dict[str, Any],
    as_of: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    held_symbols = {str(row.get("symbol") or "").upper() for row in positions}
    stop_multiple = _number(((spec.get("risk") or {}).get("initial_stop") or {}).get("multiple")) or 2.0
    for order in orders:
        order_date = str(_field(order, "submitted_at", ""))[:10]
        status = str(_field(order, "status", "")).upper()
        if order_date != as_of[:10] or status not in {"SUBMITTED", "PENDING", ""}:
            continue
        side = str(_field(order, "side", "n/a")).upper()
        symbol = str(_field(order, "symbol", "n/a")).upper()
        quantity = int(_number(_field(order, "quantity")) or 0)
        mark = marks.get(symbol, {})
        reference_price = _number(mark.get("close"))
        atr = _number(mark.get("atr_14"))
        stop_price = _number(_field(order, "stop_price"))
        if stop_price is None and side == "BUY" and reference_price and atr and atr > 0:
            stop_price = max(0.0, reference_price - stop_multiple * atr)
        target_price = None
        risk_per_share = reference_price - stop_price if reference_price is not None and stop_price is not None else None
        if risk_per_share is not None and risk_per_share > 0:
            target_price = reference_price + 2.0 * risk_per_share
        trade_intent = "EXIT" if side == "SELL" else "ADD" if symbol in held_symbols else "ENTRY"
        rows.append(
            {
                "date": order_date,
                "order_id": str(_field(order, "order_id", "n/a")),
                "strategy_id": str(_field(order, "strategy_id", "n/a")),
                "symbol": symbol,
                "side": side,
                "trade_intent": trade_intent,
                "quantity": quantity,
                "order_type": str(_field(order, "order_type", "n/a")),
                "signal_reason": str(_field(order, "reason", "n/a")),
                "reference_price": _round(reference_price),
                "stop_price": _round(stop_price),
                "target_price": _round(target_price),
                "risk_per_share": _round(risk_per_share if risk_per_share and risk_per_share > 0 else None),
                "estimated_risk": _round((risk_per_share * quantity) if risk_per_share and risk_per_share > 0 else None),
                "estimated_notional": _round((reference_price * quantity) if reference_price is not None else None),
            }
        )
    return sorted(rows, key=lambda row: (str(row.get("trade_intent")), str(row.get("symbol"))))


def _trade_rows(
    fills: list[Any],
    *,
    orders: list[Any] | None = None,
    feature_marks: dict[tuple[str, str], dict[str, Any]] | None = None,
    spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    orders_by_id = {str(_field(order, "order_id", "")): order for order in (orders or [])}
    marks = feature_marks or {}
    stop_multiple = _number((((spec or {}).get("risk") or {}).get("initial_stop") or {}).get("multiple")) or 2.0
    lots: dict[str, list[dict[str, Any]]] = {}
    for fill in fills:
        side = str(_field(fill, "side", "n/a")).upper()
        quantity = int(_number(_field(fill, "quantity")) or 0)
        price = _number(_field(fill, "price", _field(fill, "fill_price"))) or 0.0
        fees = _number(_field(fill, "fees")) or 0.0
        notional = quantity * price
        date = str(_field(fill, "timestamp", _field(fill, "fill_date", "n/a")))
        symbol = str(_field(fill, "symbol", "n/a")).upper()
        order = orders_by_id.get(str(_field(fill, "order_id", "")), {})
        mark = marks.get((date[:10], symbol), {})
        atr = _number(mark.get("atr_14"))
        stop_price = _number(_field(order, "stop_price"))
        if stop_price is None and side == "BUY" and atr and atr > 0:
            stop_price = max(0.0, price - stop_multiple * atr)
        target_price = None
        risk_per_share = price - stop_price if stop_price is not None else None
        if risk_per_share is not None and risk_per_share > 0:
            target_price = price + 2.0 * risk_per_share

        entry_date = date
        entry_price = price
        risk_amount = risk_per_share * quantity if risk_per_share is not None and risk_per_share > 0 else None
        realized_pnl = None
        r_multiple = None
        holding_period_days = None
        if side == "SELL":
            attribution = _consume_trade_lots(lots.get(symbol, []), quantity, price, fees, date)
            entry_date = attribution.get("entry_date") or date
            entry_price = _number(attribution.get("entry_price")) or price
            stop_price = _number(attribution.get("stop_price"))
            target_price = _number(attribution.get("target_price"))
            risk_amount = _number(attribution.get("risk_amount"))
            realized_pnl = _number(attribution.get("realized_pnl"))
            r_multiple = _number(attribution.get("r_multiple"))
            holding_period_days = attribution.get("holding_period_days")
        elif side == "BUY" and quantity > 0:
            lots.setdefault(symbol, []).append(
                {
                    "quantity": quantity,
                    "entry_date": date,
                    "entry_price": price,
                    "stop_price": stop_price,
                    "target_price": target_price,
                }
            )
        rows.append(
            {
                "date": date,
                "strategy_id": str(_field(fill, "strategy_id", "n/a")),
                "symbol": symbol,
                "side": side,
                "trade_intent": "ENTRY" if side == "BUY" else "EXIT" if side == "SELL" else "n/a",
                "signal_date": str(_field(order, "submitted_at", ""))[:10],
                "signal_reason": str(_field(order, "reason", "n/a")),
                "order_type": str(_field(order, "order_type", "n/a")),
                "entry_date": entry_date,
                "quantity": quantity,
                "price": _round(price),
                "entry_price": _round(entry_price),
                "stop_price": _round(stop_price),
                "target_price": _round(target_price),
                "risk_amount": _round(risk_amount),
                "realized_pnl": _round(realized_pnl),
                "r_multiple": _round(r_multiple),
                "holding_period_days": holding_period_days,
                "notional": _round(notional),
                "fees": _round(fees),
                "slippage": _round(_field(fill, "slippage")),
                "cash_effect": _round(notional - fees if side == "SELL" else -notional - fees),
                "order_id": str(_field(fill, "order_id", "n/a")),
                "fill_id": str(_field(fill, "fill_id", "n/a")),
            }
        )
    return rows


def _consume_trade_lots(
    lots: list[dict[str, Any]],
    quantity: int,
    sell_price: float,
    fees: float,
    sell_date: str,
) -> dict[str, Any]:
    remaining = quantity
    consumed: list[dict[str, Any]] = []
    while remaining > 0 and lots:
        lot = lots[0]
        lot_qty = int(_number(lot.get("quantity")) or 0)
        take = min(remaining, lot_qty)
        consumed.append({**lot, "quantity": take})
        remaining -= take
        lot["quantity"] = lot_qty - take
        if lot["quantity"] <= 0:
            lots.pop(0)
    if not consumed or quantity <= 0:
        return {}
    weighted_entry = sum((_number(lot.get("entry_price")) or sell_price) * int(lot["quantity"]) for lot in consumed) / quantity
    stop_values = [_number(lot.get("stop_price")) for lot in consumed if _number(lot.get("stop_price")) is not None]
    target_values = [_number(lot.get("target_price")) for lot in consumed if _number(lot.get("target_price")) is not None]
    stop_price = sum(stop_values) / len(stop_values) if stop_values else None
    target_price = sum(target_values) / len(target_values) if target_values else None
    realized_pnl = (sell_price - weighted_entry) * quantity - fees
    risk_per_share = weighted_entry - stop_price if stop_price is not None else None
    risk_amount = risk_per_share * quantity if risk_per_share is not None and risk_per_share > 0 else None
    r_multiple = (sell_price - weighted_entry) / risk_per_share if risk_per_share is not None and risk_per_share > 0 else None
    first_entry_date = str(consumed[0].get("entry_date") or "")
    return {
        "entry_date": first_entry_date,
        "entry_price": weighted_entry,
        "stop_price": stop_price,
        "target_price": target_price,
        "risk_amount": risk_amount,
        "realized_pnl": realized_pnl,
        "r_multiple": r_multiple,
        "holding_period_days": _days_between(first_entry_date, sell_date),
    }


def _agent_actions(portfolio_state: dict[str, Any], selected: dict[str, Any], trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    as_of = portfolio_state["as_of"]
    strategy_id = portfolio_state["selected_strategy_id"]
    latest_trade_date = max((str(row.get("date")) for row in trades), default="n/a")
    return [
        {
            "timestamp": as_of,
            "agent": "strategy_selection_agent",
            "action": "select_strategy",
            "strategy_id": strategy_id,
            "reason": portfolio_state["selection_reason"],
            "payload": {"rank": selected.get("rank"), "rank_score": selected.get("rank_score")},
        },
        {
            "timestamp": as_of,
            "agent": "portfolio_manager_agent",
            "action": "publish_daily_state",
            "strategy_id": strategy_id,
            "reason": "Published current paper holdings, cash, NAV, and unrealized P&L.",
            "payload": {"open_positions": portfolio_state["open_positions"], "today_pnl": portfolio_state["today_pnl"]},
        },
        {
            "timestamp": as_of,
            "agent": "trading_agent",
            "action": "replay_eod_trades",
            "strategy_id": strategy_id,
            "reason": "Replayed deterministic next-open fills from EOD signals.",
            "payload": {"fills": len(trades), "latest_trade_date": latest_trade_date},
        },
        {
            "timestamp": as_of,
            "agent": "monitoring_agent",
            "action": "risk_snapshot",
            "strategy_id": strategy_id,
            "reason": "Calculated stops, targets, mark-to-market exposure, and daily P&L.",
            "payload": {
                "total_market_value": portfolio_state["total_market_value"],
                "total_unrealized_pnl": portfolio_state["total_unrealized_pnl"],
            },
        },
        {
            "timestamp": as_of,
            "agent": "report_agent",
            "action": "write_paper_portfolio_report",
            "strategy_id": strategy_id,
            "reason": "Rendered comprehensive paper portfolio report.",
            "payload": {"report": portfolio_state["artifacts"]["report"]},
        },
    ]


def _paper_report(
    portfolio_state: dict[str, Any],
    positions: list[dict[str, Any]],
    daily_pnl: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    next_orders: list[dict[str, Any]] | None = None,
) -> str:
    latest = daily_pnl[-1] if daily_pnl else {}
    recent_trades = trades[-20:]
    latest_trade_date = max((str(row.get("date")) for row in trades), default="")
    today_trades = [row for row in trades if str(row.get("date")) == portfolio_state["as_of"]]
    if not today_trades and latest_trade_date:
        today_trades = [row for row in trades if str(row.get("date")) == latest_trade_date]
    buys_today = [row for row in today_trades if row.get("side") == "BUY"]
    sells_today = [row for row in today_trades if row.get("side") == "SELL"]
    exposure = (
        (_number(latest.get("market_value")) or 0.0) / (_number(latest.get("nav")) or 1.0) * 100.0
        if _number(latest.get("nav"))
        else 0.0
    )
    lines = [
        "# Daily Paper Portfolio Report",
        "",
        f"As of: `{portfolio_state['as_of']}`",
        f"Selected strategy: `{portfolio_state['selected_strategy_id']}` - {portfolio_state['selected_strategy_name']}",
        "",
        "## Current Paper Book",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Open Positions | {portfolio_state.get('open_positions', 0)} |",
        f"| Cash | {_fmt_rs(latest.get('cash'))} |",
        f"| Market Value | {_fmt_rs(latest.get('market_value'))} |",
        f"| Exposure | {_fmt(exposure)}% |",
        f"| Latest Trade Date | {latest_trade_date or 'n/a'} |",
        f"| Buys In Blotter | {len(buys_today)} |",
        f"| Sells In Blotter | {len(sells_today)} |",
        "",
        "## P&L Snapshot",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| NAV | {_fmt_rs(latest.get('nav'))} |",
        f"| Cash | {_fmt_rs(latest.get('cash'))} |",
        f"| Market Value | {_fmt_rs(latest.get('market_value'))} |",
        f"| Daily P&L | {_fmt_rs(latest.get('daily_pnl'))} |",
        f"| Daily Return | {_fmt(latest.get('daily_return_pct'))}% |",
        f"| Drawdown | {_fmt(latest.get('drawdown_pct'))}% |",
        f"| Unrealized P&L | {_fmt_rs(portfolio_state.get('total_unrealized_pnl'))} |",
        "",
        "## Open Positions",
        "",
        "| Symbol | Qty | Price | Avg Cost | Unrealized | Stop | Target | Stage | RS |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    if positions:
        for row in positions:
            lines.append(
                f"| {row['symbol']} | {row['quantity']} | {_fmt_rs(row['current_price'])} | {_fmt_rs(row['avg_cost'])} | "
                f"{_fmt_rs(row['unrealized_pnl'])} | {_fmt_rs(row['stop_price'])} | {_fmt_rs(row['target_price'])} | "
                f"{row['stage']} | {_fmt(row['relative_strength'])} |"
            )
    else:
        lines.append("| n/a | 0 | ₹0.00 | ₹0.00 | ₹0.00 | n/a | n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Today Trade Blotter",
            "",
            "| Date | Symbol | Action | Qty | Price | Reason | Entry | Stop | Target | Realized | R | Hold Days |",
            "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if today_trades:
        for row in today_trades:
            lines.append(
                f"| {row['date']} | {row['symbol']} | {row.get('trade_intent', row['side'])} | {row['quantity']} | "
                f"{_fmt_rs(row['price'])} | {row.get('signal_reason', 'n/a')} | {_fmt_rs(row.get('entry_price'))} | "
                f"{_fmt_rs(row.get('stop_price'))} | {_fmt_rs(row.get('target_price'))} | "
                f"{_fmt_rs(row.get('realized_pnl'))} | {_fmt(row.get('r_multiple'))} | {_fmt(row.get('holding_period_days'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | 0 | ₹0.00 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Next Session Orders",
            "",
            "| Date | Order | Symbol | Action | Qty | Type | Reason | Ref Price | Stop | Target | Est Risk | Est Notional |",
            "|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    if next_orders:
        for row in next_orders:
            lines.append(
                f"| {row.get('date')} | {row.get('order_id')} | {row.get('symbol')} | {row.get('trade_intent')} | "
                f"{row.get('quantity')} | {row.get('order_type')} | {row.get('signal_reason')} | "
                f"{_fmt_rs(row.get('reference_price'))} | {_fmt_rs(row.get('stop_price'))} | "
                f"{_fmt_rs(row.get('target_price'))} | {_fmt_rs(row.get('estimated_risk'))} | "
                f"{_fmt_rs(row.get('estimated_notional'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | HOLD | 0 | n/a | no next-open paper orders | n/a | n/a | n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Recent Trades",
            "",
            "| Date | Symbol | Side | Intent | Qty | Price | Reason | Realized | Hold Days |",
            "|---|---|---|---|---:|---:|---|---:|---:|",
        ]
    )
    if recent_trades:
        for row in recent_trades:
            lines.append(
                f"| {row['date']} | {row['symbol']} | {row['side']} | {row.get('trade_intent', 'n/a')} | "
                f"{row['quantity']} | {_fmt_rs(row['price'])} | {row.get('signal_reason', 'n/a')} | "
                f"{_fmt_rs(row.get('realized_pnl'))} | {_fmt(row.get('holding_period_days'))} |"
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | 0 | ₹0.00 | n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Agent Audit",
            "",
            "| Agent | Action | Purpose |",
            "|---|---|---|",
            "| strategy_selection_agent | select_strategy | Selects the daily paper strategy from the leaderboard |",
            "| portfolio_manager_agent | publish_daily_state | Publishes holdings, cash, NAV, and P&L |",
            "| trading_agent | replay_eod_trades | Replays deterministic EOD signals and next-open fills |",
            "| monitoring_agent | risk_snapshot | Calculates stops, targets, exposure, and drawdown |",
            "| report_agent | write_paper_portfolio_report | Generates this report |",
            "",
            "*Paper trading only. No broker orders are placed.*",
        ]
    )
    return "\n".join(lines) + "\n"


def _field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    value = getattr(row, name, default)
    if hasattr(value, "value"):
        return value.value
    return value


def _days_between(start: str, end: str) -> int | None:
    try:
        start_date = pd.to_datetime(start).date()
        end_date = pd.to_datetime(end).date()
    except Exception:
        return None
    return (end_date - start_date).days


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _round(value: Any) -> float | None:
    parsed = _number(value)
    if parsed is None:
        return None
    return round(parsed, 6)


def _format_strategy_ids(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value) or "n/a"
    return str(value)


def _exit_trigger(stop_price: float | None) -> str:
    if stop_price is None:
        return "strategy exit rules"
    return f"strategy exit rules or close below {stop_price:.2f}"


def _fmt(value: Any) -> str:
    parsed = _number(value)
    return "n/a" if parsed is None else f"{parsed:,.2f}"


def _fmt_rs(value: Any) -> str:
    parsed = _number(value)
    return "n/a" if parsed is None else f"₹{parsed:,.2f}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, str) or value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
