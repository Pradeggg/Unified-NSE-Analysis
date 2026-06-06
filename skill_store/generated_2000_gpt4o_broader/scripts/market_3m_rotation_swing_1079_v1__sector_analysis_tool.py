def run(context):
    # This function processes sector data to determine top sectors
    sector_count = {}
    for data in context['sector_data']:
        sector = data['sector']
        if sector not in sector_count:
            sector_count[sector] = 0
        sector_count[sector] += 1
    sorted_sectors = sorted(sector_count.items(), key=lambda x: x[1], reverse=True)
    return {'top_sectors': sorted_sectors}