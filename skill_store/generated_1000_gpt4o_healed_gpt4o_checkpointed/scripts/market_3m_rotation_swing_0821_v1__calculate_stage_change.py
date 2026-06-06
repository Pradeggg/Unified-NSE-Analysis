def run(context):
    # Extract necessary data from context
    stage_data = context['scores.stage_snapshots']
    # Perform calculations (mock example)
    stage_distribution_change = {'stage_1': 0.1, 'stage_2': 0.3, 'stage_3': -0.2, 'stage_4': -0.2}
    # Return the mock calculation results
    return {'stage_distribution_change': stage_distribution_change}