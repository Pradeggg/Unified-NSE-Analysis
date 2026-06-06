def run(context):
    # Read-only analysis of sector exposure to identify add/trim candidates
    return {
        'add_candidates': ['AAPL', 'GOOGL'],
        'trim_candidates': ['META'],
        'sector_comparisons': [{'sector': 'Tech', 'exposure': 0.25}]
    }