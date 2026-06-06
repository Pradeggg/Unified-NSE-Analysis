def run(context):
    # Ensure 'index_returns' and 'sector_volatility' are provided in context
    index_returns = context.get('index_returns', [])
    sector_volatility = context.get('sector_volatility', [])
    if not index_returns or not sector_volatility:
        return {'risk_assessment': 'data_missing'}

    index_mean_return = sum(index_returns) / len(index_returns)
    sector_vol_mean = sum(sector_volatility) / len(sector_volatility)
    risk_score = index_mean_return / sector_vol_mean
    return {'risk_assessment': risk_score}