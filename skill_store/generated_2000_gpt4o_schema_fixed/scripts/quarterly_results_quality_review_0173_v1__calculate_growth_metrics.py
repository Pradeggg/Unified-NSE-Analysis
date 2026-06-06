
    def run(context):
        revenue_growth = (context['revenue'][-1] - context['revenue'][0]) / context['revenue'][0] * 100
        pat_growth = (context['pat'][-1] - context['pat'][0]) / context['pat'][0] * 100
        return {'growth_metrics': {'revenue_growth': revenue_growth, 'pat_growth': pat_growth}}
        