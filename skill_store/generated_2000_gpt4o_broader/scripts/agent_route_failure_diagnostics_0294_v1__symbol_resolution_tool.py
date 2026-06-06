def run(context):
    resolved_symbols = context['filtered_symbols']
    snapshot_data = context['stage_snapshots']
    # Analyze discrepancies
    discrepancies = resolved_symbols.difference(snapshot_data)
    return discrepancies