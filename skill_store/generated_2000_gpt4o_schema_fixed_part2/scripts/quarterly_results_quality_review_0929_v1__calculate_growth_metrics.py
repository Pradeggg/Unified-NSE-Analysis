def run(context):
    revenue_growth = (context['revenue_current_period'] - context['revenue_last_period']) / context['revenue_last_period'] * 100
    pat_growth = (context['pat_current_period'] - context['pat_last_period']) / context['pat_last_period'] * 100
    return {'revenue_growth': revenue_growth, 'pat_growth': pat_growth}