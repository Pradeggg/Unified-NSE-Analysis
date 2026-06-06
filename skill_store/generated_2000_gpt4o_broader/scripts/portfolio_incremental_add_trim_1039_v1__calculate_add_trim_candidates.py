def run(context):
    add_candidates = []
    trim_candidates = []
    # Example logic: Add candidates based on price increase and trim candidates where RSI is high
    for holding in context['holdings_data']:
        if holding['change_1m_pct'] > 5:
            add_candidates.append(holding['symbol'])
        if holding['rsi'] > 70:
            trim_candidates.append(holding['symbol'])
    return add_candidates, trim_candidates