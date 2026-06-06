def run(context):
    context['suggested_watchlist'] = context['avg_stage2_pct'] + context['rs_momentum']
    return context