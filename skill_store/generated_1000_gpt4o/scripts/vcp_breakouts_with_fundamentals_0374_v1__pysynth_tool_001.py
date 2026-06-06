def run(context):
    return [data for data in context['vcp_data'] if data['enhanced_fund_score'] > 70]