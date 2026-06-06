def run(context):
    risk_factors = context['results_data']['verdict']
    risk_score = sum(factor_score.get(factor, 0) for factor in risk_factors)
    return {'risk_score': risk_score}