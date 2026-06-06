def run(context):
    # Extract and process SQL query results
    results = context['SQL_query_results']
    ranked_candidates = sorted(results, key=lambda x: x['return_pct'], reverse=True)
    return ranked_candidates[:10]