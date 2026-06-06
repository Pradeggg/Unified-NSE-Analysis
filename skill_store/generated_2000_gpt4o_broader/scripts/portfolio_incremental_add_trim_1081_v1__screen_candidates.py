def run(context):
    # Context provides holdings_data and snapshots_data
    add_candidates = []
    trim_candidates = []
    # Example processing logic
    for holding in context['holdings_data']:
        symbol = holding['symbol']
        snapshot = next((item for item in context['snapshots_data'] if item['symbol'] == symbol), None)
        if snapshot:
            if snapshot['change_1d_pct'] > 2 and snapshot['stage_score'] > 80:
                add_candidates.append(symbol)
            elif snapshot['change_1d_pct'] < -2 and snapshot['stage_score'] < 40:
                trim_candidates.append(symbol)
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}