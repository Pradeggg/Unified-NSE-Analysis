def run(context):
    growth_summary = {}
    for entry in context['entries']:
        revenue_growth = entry['growth_yoy_revenue_pct']
        pat_growth = entry['growth_yoy_pat_pct']
        if revenue_growth > 20 and pat_growth > 20:
            growth_summary[entry['symbol']] = 'Strong Growth'
        elif revenue_growth > 0 and pat_growth > 0:
            growth_summary[entry['symbol']] = 'Moderate Growth'
        else:
            growth_summary[entry['symbol']] = 'Weak or Negative Growth'
    return growth_summary