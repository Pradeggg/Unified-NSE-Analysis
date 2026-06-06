def run(context):
    # Example Python tool that ranks companies based on PAT growth and margin improvements
    results = context
    ranked_results = sorted(results, key=lambda x: (x['growth_yoy_pat_pct'], x['opm_pct']), reverse=True)
    return {'ranking': ranked_results}