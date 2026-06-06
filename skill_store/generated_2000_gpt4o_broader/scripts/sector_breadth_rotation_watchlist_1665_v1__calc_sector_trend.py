def run(context):
    trend = 'upward' if context['change_5d'] > 0 else 'downward'
    return {'trend_direction': trend}