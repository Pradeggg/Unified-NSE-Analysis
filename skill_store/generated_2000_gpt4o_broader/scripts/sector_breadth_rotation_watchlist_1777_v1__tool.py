# Sample function to parse sector data and generate a candidate watchlist
def run(context):
    improving_sectors = [sector for sector in context if sector['change_5d'] > 0 and sector['stage'] == 2]
    return {'watchlist': improving_sectors}