def run(context):
    risk_flags = []
    for snapshot in context['snapshots']:
        if snapshot['stage_score'] < 50 or snapshot['change_1m_pct'] < 0:
            risk_flags.append('HIGH_RISK')
        else:
            risk_flags.append('LOW_RISK')
    return risk_flags