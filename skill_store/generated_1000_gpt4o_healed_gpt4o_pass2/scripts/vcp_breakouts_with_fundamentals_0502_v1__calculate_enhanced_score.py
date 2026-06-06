def run(context): 
    return context['fundamental_score'] * 1.2 if context.get('market_cap_cr', 0) > 500 else context['fundamental_score']