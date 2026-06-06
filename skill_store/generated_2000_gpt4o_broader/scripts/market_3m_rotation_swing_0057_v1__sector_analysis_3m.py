def run(context):
    # Analyze top performing sectors
    data = context['relative_strength_data']
    leader_sector_summary = data.groupby('sector').agg({'relative_strength': 'mean'}).sort_values(by='relative_strength', ascending=False).head(5)
    return leader_sector_summary