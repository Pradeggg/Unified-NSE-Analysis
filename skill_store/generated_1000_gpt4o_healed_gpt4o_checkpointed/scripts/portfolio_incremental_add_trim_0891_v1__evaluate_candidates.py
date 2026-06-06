def run(context):
    weekly_performance_data = context.get('weekly_performance_data', [])
    add_candidates = []
    trim_candidates = []
    for record in weekly_performance_data:
        if record['change_1w_pct'] > 5:
            add_candidates.append(record['symbol'])
        elif record['change_1w_pct'] < -5:
            trim_candidates.append(record['symbol'])
    return {
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates
    }