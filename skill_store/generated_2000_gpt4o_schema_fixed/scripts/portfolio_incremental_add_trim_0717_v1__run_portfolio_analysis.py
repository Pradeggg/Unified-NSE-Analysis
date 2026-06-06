# Function to evaluate portfolio for add/trim

import pandas as pd

def run(context):
    snapshots = context.inputs['latest_stage_snapshots']
    holdings = context.inputs['join_holdings_with_stages']

    # Perform analysis
    summary = {'add_candidates': [], 'trim_candidates': []}
    for index, row in holdings.iterrows():
        if row['trading_signal'] in ['BUY', 'STRONG_BUY']:
            summary['add_candidates'].append(row['symbol'])
        elif row['trading_signal'] == 'SELL':
            summary['trim_candidates'].append(row['symbol'])

    return {'portfolio_review_summary': summary}