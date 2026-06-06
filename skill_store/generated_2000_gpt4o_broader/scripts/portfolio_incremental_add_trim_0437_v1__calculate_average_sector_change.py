def run(context):
    data = context['sector_performance_data']
    sector_changes = {}
    for entry in data:
        sector = entry['sector']
        change = entry['change_1m_pct']
        if sector in sector_changes:
            sector_changes[sector].append(change)
        else:
            sector_changes[sector] = [change]
    average_sector_change = {s: sum(changes) / len(changes) for s, changes in sector_changes.items()}
    return average_sector_change