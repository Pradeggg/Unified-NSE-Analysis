def run(context):
    # Example python code to process data
    # This is a read-only operation
    fii_trend = context['fii_dii_data']['fii_trend']
    regime_confidence = context['regime_data']['confidence']
    breadth_signal = context['breadth_data']['ad_signal']
    index_trend = context['index_data']['trend_signal']
    # Analyze and synthesize the inputs
    summary = {
        'regime': regime_confidence,
        'flow_context': fii_trend,
        'breadth_context': breadth_signal,
        'index_confirmation': index_trend,
        'risk_flags': 'Assessed based on integrated signals.'
    }
    return summary