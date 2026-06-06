def run(context):
    eod_data = context['latest_eod_data']
    stage_data = context['stage_snapshot_data']
    financial_data = context['financial_data']
    results_analysis = context['results_analysis']
    # Integrate data into comprehensive report format
    integrated_report = {
        'snapshot': eod_data,
        'financial_trends': financial_data,
        'technical_setup': stage_data,
        'narrative': results_analysis
    }
    return integrated_report