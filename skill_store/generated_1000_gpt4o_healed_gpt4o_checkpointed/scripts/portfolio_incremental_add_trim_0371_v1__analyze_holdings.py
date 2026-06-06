def run(context):
    high_stage = [h for h in context['holdings_data'] if h['stage_score'] > threshold]
    add_candidates = [h for h in high_stage if h['trading_signal'] == 'buy']
    trim_candidates = [h for h in high_stage if h['trading_signal'] == 'sell']
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates, 'risk_flags': []}