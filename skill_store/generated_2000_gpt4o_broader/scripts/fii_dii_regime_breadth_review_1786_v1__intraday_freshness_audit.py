def run(context):
    report = {}
    current_date = datetime.date.today()
    report['fii_dii_flow_freshness'] = (current_date - context['fii_dii_flows_updated_at'].date()).days
    report['regime_history_freshness'] = (current_date - context['regime_history_updated_at'].date()).days
    report['market_daily_freshness'] = (current_date - context['market_daily_updated_at'].date()).days
    report['index_eod_freshness'] = (current_date - context['index_eod_trade_date'].date()).days
    return report