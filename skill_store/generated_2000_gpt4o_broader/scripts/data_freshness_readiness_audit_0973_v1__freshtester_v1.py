def run(context):
    # Fetch the latest dates from the evidence data
    index_latest = context['market.index_eod'].get('trade_date')
    equity_latest = context['market.equity_eod'].get('trade_date')
    snapshot_latest = context['scores.stage_snapshots'].get('snapshot_date')
    
    # Create a freshness matrix to compare dates
    freshness_matrix = {
        'Index EOD Latest Date': index_latest,
        'Equity EOD Latest Date': equity_latest,
        'Stage Snapshot Latest Date': snapshot_latest
    }
    
    # Determine missing sources if any date is None
    missing_sources = [source for source, date in freshness_matrix.items() if date is None]
    
    return freshness_matrix, missing_sources