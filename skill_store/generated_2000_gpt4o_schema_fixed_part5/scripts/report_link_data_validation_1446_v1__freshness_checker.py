def run(context):
    # Simulate a freshness check on 'run_ts' timestamps
    threshold_date = datetime.now() - relativedelta(months=3)
    data = context['evidence_data']
    fresh_data = [item for item in data if item['run_ts'] >= threshold_date]
    return { 'freshness_report': fresh_data }