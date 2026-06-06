def run(context):
    risks = []
    for ret in context['index_returns']:
        risk = ret * (1 - context['investment_score']['average'])
        risks.append(risk)
    return {'risks': risks}