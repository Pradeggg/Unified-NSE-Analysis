def run(context):
    # Analyze FII/DII trends
    flows = context['fii_dii_flows']
    regime = context['regime_history']
    breadth = context['market_breadth']
    index = context['index_eod']
    
    # Basic scoring based on trends
    risk_on = flows['fii_trend'] == 'buy' and breadth['ad_signal'] == 'buy' and index['trend_signal'] == 'bullish'
    risk_off = flows['fii_trend'] == 'sell' or breadth['ad_signal'] == 'sell' or index['trend_signal'] == 'bearish'
    
    candidates = []

    if risk_on:
        candidates.append({'candidate': 'Buy', 'reason': 'Positive FII trends and breadth'})
    if risk_off:
        candidates.append({'candidate': 'Sell', 'reason': 'Negative market signals'})
    
    return {'ranked_candidates': sorted(candidates, key=lambda x: x['candidate']), 'risk_analysis': 'Risk-on' if risk_on else 'Risk-off' if risk_off else 'Neutral'}