def run(context):
    ranked = sorted(context['inputs'], key=lambda x: (x['insider_score'], x['technical_score']), reverse=True)
    return ranked