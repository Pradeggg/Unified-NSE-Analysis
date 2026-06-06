def run(context):
    # Evidence evaluation logic here
    issues = []
    if context['max_trade_date_eq'] < context['freshness_threshold']:
        issues.append('Equity EOD data is stale.')
    if context['max_trade_date_idx'] < context['freshness_threshold']:
        issues.append('Index EOD data is stale.')
    if context['max_snapshot_date'] < context['freshness_threshold']:
        issues.append('Stage snapshot data is stale.')
    return {
        'freshness_issues': issues,
        'sector_summary': 'Detailed sector-wise summary of freshness readiness.'
    }