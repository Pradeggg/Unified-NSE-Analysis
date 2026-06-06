def run(context):
    # Example logic to process and filter data
    candidates = []
    for record in context['tables']['scores.stage2_vcp_picks']:
        if record['vcp_score'] > 50 and record['enhanced_fund_score'] > 60:
            candidates.append(record)
    return candidates, None