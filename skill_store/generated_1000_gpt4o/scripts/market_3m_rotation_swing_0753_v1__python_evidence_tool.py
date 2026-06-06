def run(context):
    # Example code to process SQL template outputs and produce required insight
    results = {
        'index_returns': context['index_return_analysis'],
        'leading_sectors': context['sector_leadership_analysis'],
        'primary_candidates': context['stage2_vcp_candidates']
    }
    return results