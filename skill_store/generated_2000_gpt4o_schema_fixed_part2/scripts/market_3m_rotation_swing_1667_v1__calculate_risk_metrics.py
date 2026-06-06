def run(context):
    # Example logic: Calculate average risk based on index changes and candidate signals
    risks = {}
    index_total_change = sum([entry['change_pct'] for entry in context['index_returns']])
    candidate_count = len(context['primary_candidates'])
    if candidate_count > 0:
        average_risk = index_total_change / candidate_count
        risks['average_risk'] = average_risk
    return risks