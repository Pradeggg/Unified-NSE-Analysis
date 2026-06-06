def run(context):
    if not isinstance(context, list):
        return []
    return [
        {
            'symbol': row['symbol'],
            'company_name': row['company_name']
        } for row in context if row.get('vcp_score', 0) > 80 and row.get('enhanced_fund_score', 0) > 70
    ]