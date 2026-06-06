def run(context):
    results = context['query_results']
    summary = {
        'total_signals': len(results),
        'hits': sum(1 for r in results if r['hit_target']),
        'stops': sum(1 for r in results if r['hit_stop'])
    }
    return {'outcome_summary': summary}