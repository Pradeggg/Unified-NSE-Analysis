def run(context):
    filtered_stocks = [s for s in context['stocks_data'] if s['vcp_score'] > 80 and s['enhanced_fund_score'] > 70]
    return filtered_stocks