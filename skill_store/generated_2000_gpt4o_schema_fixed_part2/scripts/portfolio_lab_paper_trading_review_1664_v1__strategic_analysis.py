def run(context):
    # Analyze signals and holdings to determine strategy states and entry/exit rules
    # This is a read-only function following Python tool policy
    signal_data = context['signal_log_with_outcomes']
    holdings_data = context['portfolio_holdings_with_latest_stage']
    # Business logic goes here
    strategy_state = {}
    entry_exit_rules = {}
    return {
        'strategy_state': strategy_state,
        'entry_exit_rules': entry_exit_rules
    }