def run(context):
    regime = context['regime_history'][0]['regime']
    flow_context = context['signals.fii_dii_flows'][0]['flow_signal']
    breadth_context = context['breadth.market_daily'][0]['ad_signal']
    index_confirmation = context['market.index_eod'][0]['trend_signal']
    risk_flags = 'risk-on' if regime == 'bullish' and flow_context == 'positive' and breadth_context == 'expansion' else 'risk-off'
    return {
        'regime': regime,
        'flow_context': flow_context,
        'breadth_context': breadth_context,
        'index_confirmation': index_confirmation,
        'risk_flags': risk_flags
    }