def run(context):
    symbols = context.inputs['symbols']
    tradingview_symbols = [symbol + '.NSE' for symbol in symbols]
    return {'tradingview_symbols': tradingview_symbols}