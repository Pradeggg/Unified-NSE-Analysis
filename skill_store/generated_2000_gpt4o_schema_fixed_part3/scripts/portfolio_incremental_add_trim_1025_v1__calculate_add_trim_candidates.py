def run(context):
    # Example logic, not for execution
    holdings = context['portfolio_data']
    add_candidates = [h for h in holdings if h['stage_score'] > 80 and h['trading_signal'] in ['BUY', 'STRONG_BUY']]
    trim_candidates = [h for h in holdings if h['stage_score'] < 50 or h['trading_signal'] == 'SELL']
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}