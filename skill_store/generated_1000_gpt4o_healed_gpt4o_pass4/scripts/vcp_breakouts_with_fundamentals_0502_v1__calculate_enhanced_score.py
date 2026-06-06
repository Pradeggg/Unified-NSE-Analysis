def run(context):
    return {'enhanced_score': context.get('fundamental_score', 0) * 1.2 if context.get('market_cap_cr', 0) > 500 else context.get('fundamental_score', 0)}