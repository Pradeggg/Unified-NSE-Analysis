def run(context):
    sector_performance = context['recent_sector_performance']
    holdings = context['current_holdings']
    # Logic to identify add/trim candidates
    add_candidates, trim_candidates = [], [] 
    for sector_data in sector_performance:
        if sector_data['avg_weekly_change'] > 0.05:
            # Sector is robust, consider hold positions for addition
            for holding in holdings:
                if holding['sector'] == sector_data['sector']:
                    add_candidates.append(holding['symbol'])
        elif sector_data['avg_weekly_change'] < -0.05:
            # Sector is weak, consider trim positions in that sector
            for holding in holdings:
                if holding['sector'] == sector_data['sector']:
                    trim_candidates.append(holding['symbol'])
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}