def run(context):
    # Example read-only logic for sector-relative rankings
    industry_groups = {}
    for company in context:
        symbol = company['symbol']
        industry = company['industry']
        rank_metric = (company['growth_yoy_revenue_pct'] + company['growth_yoy_pat_pct'] + float(company['opm_delta_pp'])) / 3
        if industry not in industry_groups:
            industry_groups[industry] = []
        industry_groups[industry].append({'symbol': symbol, 'rank_metric': rank_metric})
    # Sort each industry group by the rank_metric
    ranked_companies = {industry: sorted(companies, key=lambda x: x['rank_metric'], reverse=True) for industry, companies in industry_groups.items()}
    return ranked_companies