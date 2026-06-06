def run(context):
    successful = [s for s in context['signals'] if s['hit_target']]
    failed = [s for s in context['signals'] if s['hit_stop']]
    trends = {
        'total': len(context['signals']),
        'successful': len(successful),
        'failed': len(failed)
    }
    return trends