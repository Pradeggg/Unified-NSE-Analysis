def run(context):
    equity_eod_data = context['equity_eod_data']
    vcp_pick_data = context['vcp_pick_data']
    filtered_candidates = []
    for vcp in vcp_pick_data:
        if vcp['vcp_score'] > 70 and vcp['enhanced_fund_score'] > 70:
            symbol = vcp['symbol']
            eod_data = next((eod for eod in equity_eod_data if eod['symbol'] == symbol), None)
            if eod_data:
                filtered_candidates.append({
                    'symbol': symbol,
                    'company_name': vcp['company_name'],
                    'sector': vcp['sector'],
                    'live_price': vcp['live_price'],
                    'change_1w_pct': vcp['change_1w_pct'],
                    'enhanced_fund_score': vcp['enhanced_fund_score']
                })
    return filtered_candidates