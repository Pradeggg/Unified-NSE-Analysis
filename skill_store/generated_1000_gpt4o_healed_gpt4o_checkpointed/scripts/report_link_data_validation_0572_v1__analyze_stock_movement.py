def run(context):
    trends = []
    if 'stock_details' in context:
        for stock in context['stock_details']:
            trend = {}
            if stock.get('day_change_pct', 0) > 0:
                trend['trend'] = 'positive'
            else:
                trend['trend'] = 'negative'
            trend['symbol'] = stock.get('symbol', 'N/A')
            trends.append(trend)
    else:
        return {'error': 'missing stock_details in context'}
    return {'categorized_trends': trends}