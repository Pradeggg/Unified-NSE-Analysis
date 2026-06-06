def run(context):
    improving_sectors = []
    for sector in context['sector data']:
        if sector['breadth_signal'] == 'improving' and sector['divergence_alert'] == 'none':
            improving_sectors.append(sector['sector'])
    return improving_sectors