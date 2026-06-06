def run(context):
    revenue_risk = max(context['growth_yoy_revenue_pct']) < 0
    pat_risk = max(context['growth_yoy_pat_pct']) < 0
    margin_risk = min(context['opm_delta_pp']) < 0
    risks_summary = []
    if revenue_risk:
        risks_summary.append('Revenue decline detected.')
    if pat_risk:
        risks_summary.append('Profit after tax decline detected.')
    if margin_risk:
        risks_summary.append('Operating margin contraction detected.')
    return risks_summary