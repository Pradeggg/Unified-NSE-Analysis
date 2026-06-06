def run(context):
    risk_factors = context['risk_factors']
    risk_assessment = sum(risk_factors) / len(risk_factors) if risk_factors else 0
    return {'risk_assessment': risk_assessment}