def run(context):
    trend_data = context['trend_signal_data']
    insights = analyze_trend_signals(trend_data)
    return {'trend_insights': insights}