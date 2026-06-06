def run(context):
    import pandas as pd
    sector_data = context['sector_data']
    ranked_sectors = sector_data.sort_values(by='stage2_pct', ascending=False)
    return ranked_sectors.head(10)