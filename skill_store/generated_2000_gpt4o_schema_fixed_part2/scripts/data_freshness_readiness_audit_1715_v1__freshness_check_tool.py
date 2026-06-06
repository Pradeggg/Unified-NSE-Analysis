def run(context):
    latest_dates = [entry['latest_date'] for entry in context['freshness_matrix']]
    any_outdated = any(date < context['expected_latest_date'] for date in latest_dates)
    return {'assessment_summary': f'All data fresh: {not any_outdated}'}