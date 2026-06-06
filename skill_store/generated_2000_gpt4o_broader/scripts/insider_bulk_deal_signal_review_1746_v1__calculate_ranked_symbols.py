def run(context):
    insider_alerts = context['insider_context']
    tech_confirms = context['technical_confirmation']
    combined = []
    for symbol in insider_alerts:
        if symbol in tech_confirms:
            combined.append((symbol, tech_confirms[symbol]['technical_score']))
    ranked = sorted(combined, key=lambda x: x[1], reverse=True)
    return ranked