def run(context):
    filtered_data = context['stocks_filtered']
    # Example logic for position sizing
    return [{'symbol': stock['symbol'], 'size': stock['score'] * 100} for stock in filtered_data]