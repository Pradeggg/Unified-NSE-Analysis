def run_sector_analysis(sql_result):
    # Extract improving sectors based on change
    improving_sectors = sql_result.head(3)['sector'].tolist()
    return {'improving_sectors': improving_sectors}