def run(context):
    # Analyze context data to find tool gaps
    analysis_results = {'missing_tools': [], 'invalid_symbols': []}
    # Example: search for missing tools in context
    if 'required_tools' not in context:
        analysis_results['missing_tools'].append('tool_list_unavailable')
    return analysis_results