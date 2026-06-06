def run(context):
    # Analyze the sector distribution and identify the leading sectors
    sector_counts = context['sector_stage_distribution'].value_counts()
    leading_sectors = sector_counts.nlargest(3)
    return leading_sectors.to_dict()