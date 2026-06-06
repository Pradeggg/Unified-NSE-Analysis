def run(context):
    capital_weight = context['market_cap'] / 1000
    volume_weight = context['trading_volume'] / 10000
    liquidity_score = capital_weight * volume_weight
    return {'liquidity_score': liquidity_score}