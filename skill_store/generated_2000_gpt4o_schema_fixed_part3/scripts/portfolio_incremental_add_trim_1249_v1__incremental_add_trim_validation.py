def run(context):
    # Perform source-trail validation
    holdings = context['portfolio_holdings']
    stage_data = context['stage_snapshot_data']
    validated_candidates = []
    for holding in holdings:
        symbol_data = next((item for item in stage_data if item['symbol'] == holding['symbol']), None)
        if symbol_data and symbol_data['trading_signal'] in ['BUY', 'STRONG_BUY']:
            validated_candidates.append({
                'symbol': holding['symbol'],
                'investment_score': symbol_data['investment_score']
            })
    return sorted(validated_candidates, key=lambda x: x['investment_score'], reverse=True)