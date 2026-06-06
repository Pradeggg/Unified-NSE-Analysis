def run(context):
    # Intended for creating a concise review by analyzing properties of paper trading strategies
    # Gather recent snapshots and match with signal outcomes
    result_table = context['scores.stage_snapshots'].merge(
        context['signals.signal_log'],
        how='inner',
        left_on=['symbol'],
        right_on=['symbol']
    )
    # Filter resolved trades and return as concise table format
    result_table = result_table[result_table['date_resolved'].notnull()]
    return result_table[['snapshot_date', 'symbol', 'stage', 'stage_score', 'signal', 'entry_low', 'entry_high', 'stop_loss', 'target_1', 'target_2', 'price_at_resolution', 'return_pct']]