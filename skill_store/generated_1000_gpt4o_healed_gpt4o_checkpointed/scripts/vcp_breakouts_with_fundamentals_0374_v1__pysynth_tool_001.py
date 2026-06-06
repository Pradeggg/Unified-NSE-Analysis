def run(context):
    if 'vcp_data' in context:
        return [data for data in context['vcp_data'] if data.get('enhanced_fund_score', 0) > 70]
    return []