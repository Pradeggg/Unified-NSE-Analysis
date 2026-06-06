def run(context):
    # Dummy implementation for reading and calculating sector exposure
    # context would typically be a DataFrame or similar object
    portfolio_state = context['portfolio_state']
    sector_data = context.get('sector_data', {})
    exposure = {}
    for holding in portfolio_state:
        sector = sector_data.get(holding['symbol'], {}).get('sector', 'Unknown')
        if sector in exposure:
            exposure[sector] += holding['qty'] * holding['avg_cost']
        else:
            exposure[sector] = holding['qty'] * holding['avg_cost']
    return exposure