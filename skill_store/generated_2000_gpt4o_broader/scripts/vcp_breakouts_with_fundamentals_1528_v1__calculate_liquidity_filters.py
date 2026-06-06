def run(context):
    # Assuming context['recent_vcp_data'] contains relevant stock details
    filtered_stocks = []
    for stock in context['recent_vcp_data']:
        if stock['volume'] > 100000:  # Hypothetical liquidity condition
            filtered_stocks.append(stock)
    return filtered_stocks