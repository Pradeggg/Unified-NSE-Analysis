def run(context):
    revenue_current = context['revenue_current']
    revenue_previous = context['revenue_previous']
    pat_current = context['pat_current']
    pat_previous = context['pat_previous']
    growth_revenue_pct = ((revenue_current - revenue_previous) / revenue_previous) * 100
    growth_pat_pct = ((pat_current - pat_previous) / pat_previous) * 100
    return {
        'growth_revenue_pct': growth_revenue_pct,
        'growth_pat_pct': growth_pat_pct
    }