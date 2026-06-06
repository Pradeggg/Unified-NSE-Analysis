def run(context):
    from datetime import datetime
    current_quarter_start = datetime(datetime.now().year, ((datetime.now().month - 1) // 3) * 3 + 1, 1)
    return {'is_fresh': context['run_ts'] >= current_quarter_start}