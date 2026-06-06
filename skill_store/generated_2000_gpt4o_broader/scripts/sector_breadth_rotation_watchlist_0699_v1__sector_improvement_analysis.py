def run(sector_data):
    improving_sectors = [sector for sector in sector_data if sector['breadth_signal'] > threshold]
    return improving_sectors