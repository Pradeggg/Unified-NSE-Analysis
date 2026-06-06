def run(context):
    # Placeholder for calculating portfolio impact based on filtered stocks
    scores = [stock['score'] for stock in context if stock['recommendation'] == 'Buy']
    portfolio_impact_score = sum(scores) / len(scores) if scores else 0
    return {'portfolio_impact_score': portfolio_impact_score}