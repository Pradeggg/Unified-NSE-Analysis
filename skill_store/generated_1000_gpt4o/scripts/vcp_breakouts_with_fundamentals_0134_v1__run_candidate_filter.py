def run(context):
    result = []
    for record in context:
        if record['vcp_score'] > 80 and record['enhanced_fund_score'] > 70:
            result.append({'symbol': record['symbol'], 'company_name': record['company_name']})
    return result