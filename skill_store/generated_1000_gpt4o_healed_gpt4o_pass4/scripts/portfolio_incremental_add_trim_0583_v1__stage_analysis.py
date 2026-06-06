def run(context):
    # Analyze stages and signals to suggest add/trim
    add_candidates = []
    trim_candidates = []
    if 'stage_snapshots' in context:
        for record in context['stage_snapshots']:
            if record['trend_signal'] == 'bullish' and record['stage_score'] > 7:
                add_candidates.append(record['symbol'])
            elif record['trend_signal'] == 'bearish' and record['stage_score'] < 3:
                trim_candidates.append(record['symbol'])
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}