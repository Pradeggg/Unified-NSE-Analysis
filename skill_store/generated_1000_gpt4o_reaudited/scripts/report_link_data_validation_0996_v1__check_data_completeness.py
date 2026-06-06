def run(context):
    # Example code for checking completeness, won't access live database
    stock_data = context.inputs[0]
    missing_data_summary = {'missing_symbols': []}
    for stock in stock_data:
        if stock['current_price'] is None or stock['recommendation'] is None:
            missing_data_summary['missing_symbols'].append(stock['symbol'])
    return missing_data_summary