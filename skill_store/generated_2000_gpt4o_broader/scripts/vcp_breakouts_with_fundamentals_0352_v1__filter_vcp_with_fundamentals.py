def run(context):
    selected_stocks = []
    for stock in context['results']:
        if stock['vcp_score'] > threshold and stock['enhanced_fund_score'] > 80:
            selected_stocks.append(stock)
    return selected_stocks