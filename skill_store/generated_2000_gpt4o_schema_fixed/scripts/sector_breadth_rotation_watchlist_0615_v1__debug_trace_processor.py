def run(context):
    debug_logs = []
    for sector in context['improving_sectors']:
        debug_logs.append(f"Sector: {sector['name']}, Stage2%: {sector['stage2_pct']}")
    return {'debug_trace': debug_logs}