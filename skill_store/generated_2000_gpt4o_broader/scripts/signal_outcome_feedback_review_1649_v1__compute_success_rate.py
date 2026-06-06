def run(context):
    outcomes = context['signal_outcomes']
    success_rates = {outcome['symbol']: outcome['targets_hit'] / outcome['total_signals'] if outcome['total_signals'] > 0 else 0 for outcome in outcomes}
    return success_rates