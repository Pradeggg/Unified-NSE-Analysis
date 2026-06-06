# Verify if the TradingView export covers all stocks for the last 5 sessions
def run(context):
    missed_data = []
    for run in context['report.enhanced_runs']:
        if run['run_ts'] >= (datetime.now() - timedelta(days=5)):
            for stock in context['report.enhanced_filtered_stocks']:
                if stock['run_id'] == run['run_id'] and (stock['symbol'] is None or stock['current_price'] is None):
                    missed_data.append(stock)
    return {'missing_data_report': missed_data}