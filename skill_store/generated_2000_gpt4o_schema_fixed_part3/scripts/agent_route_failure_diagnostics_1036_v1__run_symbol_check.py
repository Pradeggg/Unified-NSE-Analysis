def run(context):
    run_ids = context['run_ids']
    unresolved_symbols = []
    # Placeholder logic to check for unresolved symbols.
    # Assume fetching data using a read-only method.
    for run_id in run_ids:
        # Perform symbolic checks per run_id.
        unresolved = check_symbols(run_id)  # assume check_symbols function exists
        unresolved_symbols.extend(unresolved)
    return {'unresolved_symbols': unresolved_symbols}