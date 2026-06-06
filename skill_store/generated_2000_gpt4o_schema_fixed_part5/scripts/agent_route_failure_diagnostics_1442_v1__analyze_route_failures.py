# Sample Python Tool
def run(context):
    # Analyze for missing symbol resolutions and suggest fixes
    unresolved_symbols = [entry for entry in context['run_data'] if entry['recommendation'] is None]
    summary_report = {
        'unresolved_count': len(unresolved_symbols),
        'unresolved_symbols': unresolved_symbols
    }
    return summary_report