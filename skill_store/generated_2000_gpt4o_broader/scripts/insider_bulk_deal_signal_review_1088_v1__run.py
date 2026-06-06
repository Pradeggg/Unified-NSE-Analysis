def run(context):
    # Extract and process data from the context for analysis
    alerts = context['insider_alerts']
    deals = context['bulk_block_deals']
    snapshots = context['stage_snapshots']
    # ... (additional processing and logic)
    return deal_summary_table