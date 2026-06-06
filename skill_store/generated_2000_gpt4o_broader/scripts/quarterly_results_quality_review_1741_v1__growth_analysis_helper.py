def run(context):
    # Process company_data to synthesize a growth summary
    growth_summary = {
        'strong_growth_companies': []
    }
    # Example processing
    for record in context['company_data']:
        if record['growth_yoy_revenue_pct'] > 20:
            growth_summary['strong_growth_companies'].append(
                record['symbol']
            )
    return growth_summary