def run(context):
    # Example logic for assessing risk
    risks = []
    for change in context['stage_distribution_change']:
        if change['distribution'] > 50:
            risks.append({'sector': change['sector'], 'risk_level': 'high'})
    return {'risks': risks}