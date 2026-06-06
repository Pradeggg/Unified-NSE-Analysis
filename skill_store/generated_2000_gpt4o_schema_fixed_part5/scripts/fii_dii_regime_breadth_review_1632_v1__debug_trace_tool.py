def run(context):
    # Simulate processing of evidence
    trace_log = []
    for record in context['flow_data']:
        trace_log.append(f"Evaluating: Trade Date {record['trade_date']}, Flow Signal: {record['flow_signal']}")
    for record in context['regime_data']:
        trace_log.append(f"Regime: {record['regime']} with Confidence: {record['confidence']}")
    for record in context['breadth_data']:
        trace_log.append(f"Market Sentiment: {record['market_sentiment']} with {record['advances']} Advances and {record['declines']} Declines")
    for record in context['index_data']:
        trace_log.append(f"Index Close: {record['close']} with Change: {record['change_pct']}% and Trend: {record['trend_signal']}")
    return {'trace_log': trace_log}