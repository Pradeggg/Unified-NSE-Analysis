def run(context):
    missing_data = []
    if 'report.enhanced_filtered_stocks' not in context:
        raise KeyError('The key report.enhanced_filtered_stocks is missing in the context.')
    for stock in context['report.enhanced_filtered_stocks']:
        if not all([stock.get('current_price'), stock.get('open_price'), stock.get('high_price')]):
            missing_data.append(stock['symbol'])
    return {
        'missing_data': missing_data,
        'verification': len(missing_data) == 0
    }