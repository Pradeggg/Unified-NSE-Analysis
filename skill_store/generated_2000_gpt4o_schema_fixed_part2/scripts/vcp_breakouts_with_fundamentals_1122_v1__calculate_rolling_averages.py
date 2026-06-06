def run(context):
    data = context['data']
    data['rolling_avg'] = data['close'].rolling(window=5).mean()
    return data[['symbol', 'rolling_avg']]