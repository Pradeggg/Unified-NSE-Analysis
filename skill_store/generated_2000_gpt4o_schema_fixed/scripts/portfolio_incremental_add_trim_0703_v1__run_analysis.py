def run(context):
    # Analyze portfolio for add/trim opportunities based on latest trading signals
    add_candidates = context['snapshot_data'].query("trading_signal in ['BUY', 'STRONG_BUY']").symbol.tolist()
    trim_candidates = context['snapshot_data'].query("trading_signal == 'SELL'").symbol.tolist()
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}