def run(context):
    risk_flags = {}
    for entry in context:
        risk_score = entry['stage_score'] + entry['technical_score'] + entry['fundamental_score']
        risk_flags[entry['symbol']] = 'High Risk' if risk_score < 50 else 'Low Risk'
    return risk_flags