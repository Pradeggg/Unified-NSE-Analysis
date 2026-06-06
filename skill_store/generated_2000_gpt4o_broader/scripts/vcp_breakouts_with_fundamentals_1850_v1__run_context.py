# This function processes SQL results to align with the TradingView format.
def run(context):
    filtered_results = []
    for result in context['sql_results']:
        if result['vcp_score'] > 0.75 and result['enhanced_fund_score'] > 0.8:
            filtered_results.append(result)
    return filtered_results