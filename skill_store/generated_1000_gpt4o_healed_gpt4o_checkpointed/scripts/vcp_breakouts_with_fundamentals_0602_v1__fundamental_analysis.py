def run(context):
    # Placeholder for operations involving context data
    recommendation_score = compute_score(context['symbol'], context['price'])
    return {'recommendation_score': recommendation_score}