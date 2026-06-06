def run(context):
    total_market_cap = sum(context.market_cap_cr)
    exposure = [(symbol, (market_cap / total_market_cap) * 100) for symbol, market_cap in zip(context.symbol, context.market_cap_cr)]
    return exposure