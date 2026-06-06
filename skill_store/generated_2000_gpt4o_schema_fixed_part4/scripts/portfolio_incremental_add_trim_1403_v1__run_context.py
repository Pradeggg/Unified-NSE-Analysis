def run(context):
    # Sample code - pseudocode only
    latest_snapshots = context.sql("SELECT * FROM scores.stage_snapshots WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM scores.stage_snapshots)")
    latest_holdings = context.sql("SELECT * FROM portfolio.holdings")
    held_symbols = set(latest_holdings['symbol'])
    add_candidates = latest_snapshots[(latest_snapshots['trading_signal'].isin(['BUY', 'STRONG_BUY'])) & (latest_snapshots['symbol'].isin(held_symbols))]
    return {'add_candidates': add_candidates.to_dict('records')}