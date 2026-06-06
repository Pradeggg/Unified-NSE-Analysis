def run(context):
    # Logic to evaluate strategy performance
    strategy_logs = context['strategy_logs']
    market_data = context['market_data']
    # Process and return performance summary
    return {'strategy_performance_summary': {}, 'exceptions_report': {}}