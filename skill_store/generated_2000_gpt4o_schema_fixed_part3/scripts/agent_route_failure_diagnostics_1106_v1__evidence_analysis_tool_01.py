def run(context):
    # Analyze missing symbols and score discrepancies
    run_data = context['report.enhanced_runs']
    filtered_data = context['report.enhanced_filtered_stocks']
    # Perform analysis and return structured diagnostics
    analysis = perform_analysis(run_data, filtered_data)
    return analysis