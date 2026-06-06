def run(context): 
    freshness_summary = {}
    # check freshness for index_eod
    freshness_summary['index_eod'] = context['tables']['market.index_eod']['latest_trade_date']
    # check freshness for equity_eod
    freshness_summary['equity_eod'] = context['tables']['market.equity_eod']['latest_equity_date']
    # check freshness for stage_snapshots
    freshness_summary['stage_snapshots'] = context['tables']['scores.stage_snapshots']['latest_snapshot_date']
    return freshness_summary