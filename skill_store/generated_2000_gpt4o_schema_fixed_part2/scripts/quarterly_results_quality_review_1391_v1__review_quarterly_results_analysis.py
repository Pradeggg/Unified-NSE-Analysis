def run(context):
    # Analyze the latest quarterly results for notable changes
    exceptions, notable_changes = [], []
    for entry in context['data']:
        if entry['verdict'] in ['miss', 'mixed']:
            exceptions.append(entry)
        if float(entry['opm_delta_pp']) > 5.0:
            notable_changes.append(entry)
    return {'exceptions': exceptions, 'notable_changes': notable_changes}