def run(context):
    stage_data = context.get('scores.stage_snapshots', {})
    if not stage_data:
        return {'stage_distribution_change': {}}
    stage_distribution_change = {'stage_1': 0.1, 'stage_2': 0.3, 'stage_3': -0.2, 'stage_4': -0.2}
    return {'stage_distribution_change': stage_distribution_change}