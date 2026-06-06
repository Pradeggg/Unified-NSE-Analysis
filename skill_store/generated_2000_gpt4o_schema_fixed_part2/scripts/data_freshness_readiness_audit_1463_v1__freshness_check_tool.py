
    def run(context):
        current_date = context['current_system_date']
        freshness_matrix = {
            'market_index': current_date - context['latest_market_dates'],
            'equity_eod': current_date - context['latest_equity_dates'],
            'stage_snapshots': current_date - context['latest_stage_snapshot']
        }
        return freshness_matrix
    