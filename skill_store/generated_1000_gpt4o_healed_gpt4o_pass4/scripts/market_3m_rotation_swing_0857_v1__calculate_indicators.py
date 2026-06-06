def run(context):
    data = context.get('data_source', {})
    indicators = {}
    for index_data in data.get('market.index_eod', []):
        # Compute sample indicators
        indicators[index_data['index_symbol']] = {'close': index_data['close'], 'change_pct': index_data['change_pct']}
    return indicators