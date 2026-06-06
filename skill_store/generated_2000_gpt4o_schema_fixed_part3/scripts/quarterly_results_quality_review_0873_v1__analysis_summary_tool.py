def run(context):
    summary = {}
    for row in context.inputs:
        symbol = row['lr.symbol']
        summary[symbol] = {
            'verdict': row['lr.verdict'],
            'growth_yoy_revenue_pct': row['lr.growth_yoy_revenue_pct'],
            'growth_qoq_revenue_pct': row['lr.growth_qoq_revenue_pct'],
            'growth_yoy_pat_pct': row['lr.growth_yoy_pat_pct'],
            'growth_qoq_pat_pct': row['lr.growth_qoq_pat_pct'],
            'opm_pct': row['lr.opm_pct']
        }
    return summary