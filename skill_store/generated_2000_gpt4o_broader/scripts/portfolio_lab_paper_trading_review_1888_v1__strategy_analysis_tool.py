def run(context):
    # Analyze strategy performance using signals_data.
    signals_data = context['signals_data']
    analysis_result = perform_analysis(signals_data)
    return {'analysis_result': analysis_result}

# Perform_analysis is assumed to be a function that analyzes the strategy.