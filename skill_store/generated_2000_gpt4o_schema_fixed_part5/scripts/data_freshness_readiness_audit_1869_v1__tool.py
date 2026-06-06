def run(context):
    latest_index_date = context.sql('SELECT MAX(trade_date) AS latest_index_date FROM market.index_eod')
    latest_equity_date = context.sql('SELECT MAX(trade_date) AS latest_equity_date FROM market.equity_eod')
    latest_stage_date = context.sql('SELECT MAX(snapshot_date) AS latest_stage_date FROM scores.stage_snapshots')
    # Further analysis logic goes here
    return {'action_plan': 'Assess and monitor data freshness in listed sources.'}