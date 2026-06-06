def run(context):
    missing_data = []
    for stock in context['report.enhanced_filtered_stocks']:
        if not all([stock.get('current_price'), stock.get('open_price'), stock.get('high_price')]):
            missing_data.append(stock['symbol'])
    return {
        'missing_data': missing_data,
        'verification': len(missing_data) == 0
    }