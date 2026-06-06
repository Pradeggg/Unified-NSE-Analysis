def run(context):
    results = {
        'index_returns': context.get('index_return_analysis', {}),
        'leading_sectors': context.get('sector_leadership_analysis', {}),
        'primary_candidates': context.get('stage2_vcp_candidates', {})
    }
    return results