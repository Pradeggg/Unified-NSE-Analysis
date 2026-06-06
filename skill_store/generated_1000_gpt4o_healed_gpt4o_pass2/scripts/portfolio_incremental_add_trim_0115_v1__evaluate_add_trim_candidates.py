def run(context):
    snapshots = context['scores.stage_snapshots']
    holdings = context['portfolio.holdings']
    add_candidates = []
    trim_candidates = []
    risk_flags = []
    for holding in holdings:
        snapshot = next((s for s in snapshots if s['symbol'] == holding['symbol']), None)
        if snapshot:
            if snapshot['stage'] >= 4:
                trim_candidates.append({'symbol': holding['symbol'], 'reason': 'Stage >= 4'})
            elif snapshot['supertrend_state'] == 'UPTREND' and snapshot['rsi'] < 70:
                add_candidates.append({'symbol': holding['symbol'], 'reason': 'Potential growth'})
            if snapshot['relative_strength'] < 30:
                risk_flags.append({'symbol': holding['symbol'], 'reason': 'Weak relative strength'})
    return {
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates,
        'risk_flags': risk_flags
    }