def run(context):
    if not isinstance(context, list):
        return []
    return [
        {
            'symbol': row['symbol'],
            'company_name': row['company_name']
        } for row in context if row['vcp_score'] > 80 and row['enhanced_fund_score'] > 70
    ]