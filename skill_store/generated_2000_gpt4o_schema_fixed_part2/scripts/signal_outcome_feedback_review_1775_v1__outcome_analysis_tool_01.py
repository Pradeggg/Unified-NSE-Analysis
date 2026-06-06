def run(context):
    hits = [s for s in context['signal_data'] if s['hit_target'] or s['hit_stop']]
    summary = {'total': len(hits), 'successful_hits': len([s for s in hits if s['hit_target']]), 'failed_hits': len([s for s in hits if s['hit_stop']])}
    return {'analysis_summary': summary}