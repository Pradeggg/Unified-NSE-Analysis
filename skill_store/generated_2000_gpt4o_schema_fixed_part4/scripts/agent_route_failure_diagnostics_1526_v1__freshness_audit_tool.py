def run(context):
    # Extract the latest data generation timestamps
    last_five = context['evidence_required']['report.enhanced_runs'].nlargest(5, 'run_ts')
    # Check for gaps or stale data indicators
    freshness_issues = last_five['run_ts'].diff().gt(pd.Timedelta('1 days'))
    # Summarize any issues found
    return {'freshness_summary': freshness_issues.any()}