# Calculate sector-relative scores based on average performance.
# Make sure this calculation remains read-only and provides insight without changing data.
def run(context):
    sector_data = context['sector_data']
    # ... Perform calculations here
    return {'relative_sector_score': relative_sector_score}