def run(context):
    if 'vcp_data' in context:
        return {'synthesized_view': [data for data in context['vcp_data'] if data.get('enhanced_fund_score', 0) > 70]}
    return {'synthesized_view': []}