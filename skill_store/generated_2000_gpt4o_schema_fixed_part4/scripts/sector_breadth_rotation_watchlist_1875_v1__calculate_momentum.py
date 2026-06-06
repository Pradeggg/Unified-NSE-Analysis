def run(context):
    # Calculate momentum scores from provided data
    scores = [{symbol: item['symbol'], momentum: item['change_1w_pct'] + item['change_1m_pct'] for item in context['sector_data']}]
    return scores