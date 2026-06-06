# Function to rank freshness based on importance and freshness_age.
def run(context):
    ranked = sorted(context['freshness_matrix'], key=lambda x: x['freshness_age'], reverse=True)
    return {'ranked_candidates': ranked}