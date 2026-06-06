def run(context):
    add_candidates = []
    trim_candidates = []
    for record in context['weekly_performance_data']:
        if record['change_1w_pct'] > 5:
            add_candidates.append(record['symbol'])
        elif record['change_1w_pct'] < -5:
            trim_candidates.append(record['symbol'])
    return add_candidates, trim_candidates