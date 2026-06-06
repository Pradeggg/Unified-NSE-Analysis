def run(context):
    risks = context['risk_data']
    risk_score = sum(risks)
    return {'risk_score': risk_score}