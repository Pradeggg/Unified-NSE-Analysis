def run(index_data):
    # Analyzing index trends
    trends = []
    for index in index_data:
        if index['change_pct'] > 0:
            trends.append((index['index_symbol'], 'UPTREND'))
        else:
            trends.append((index['index_symbol'], 'DOWNTREND'))
    return {'trend_analysis': trends};