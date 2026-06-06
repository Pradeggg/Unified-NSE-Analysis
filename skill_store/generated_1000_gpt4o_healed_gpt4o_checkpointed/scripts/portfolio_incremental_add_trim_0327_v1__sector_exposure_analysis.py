def run(context):
    # Read-only analysis of sector exposure to identify add/trim candidates
    return {'add_candidates': ['AAPL', 'GOOGL'], 'sector_comparisons': [{'sector': 'Tech', 'exposure': 0.25}], 'trim_candidates': ['META']}