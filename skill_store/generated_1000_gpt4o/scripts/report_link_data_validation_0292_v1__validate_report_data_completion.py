def run(context):
    run_id = context['run_id']
    # Check if all mandatory data is present
    missing_data = []
    # Fetch all relevant stock data
    for stock in context['report.enhanced_filtered_stocks']:
        if not all([stock['current_price'], stock['open_price'], stock['high_price']]):
            missing_data.append(stock['symbol'])
    return {
        'missing_data': missing_data,
        'verification': len(missing_data) == 0
    }