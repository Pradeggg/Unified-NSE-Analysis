def run(context):
    # Sample Python logic for sorting companies by sector strength
    companies = context['evidence_latest_results']
    companies.sort(key=lambda x: x['growth_yoy_revenue_pct'], reverse=True)
    return companies