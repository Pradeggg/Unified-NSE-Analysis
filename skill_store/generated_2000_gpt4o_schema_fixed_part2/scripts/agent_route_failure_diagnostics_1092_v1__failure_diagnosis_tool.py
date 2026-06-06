def run(context):
    # Simple diagnostic logic
    latest_runs = context['run_data']
    symbol_analysis = context['symbol_data']
    return [{'failure_mode': 'Mismatch in tools', 'source_trail': 'Runs', 'route_fix': 'Update Toolset', 'tool_gap': 'N/A', 'regression_tests': 'Pending'}]