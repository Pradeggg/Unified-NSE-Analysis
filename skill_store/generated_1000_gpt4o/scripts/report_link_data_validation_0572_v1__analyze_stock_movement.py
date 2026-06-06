def run(context):
    trends = []
    for stock in context['stock_details']:
        trend = {}
        if stock['day_change_pct'] > 0:
            trend['trend'] = 'positive'
        else:
            trend['trend'] = 'negative'
        trend['symbol'] = stock['symbol']
        trends.append(trend)
    return {'categorized_trends': trends}