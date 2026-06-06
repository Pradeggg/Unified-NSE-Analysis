def run(context):
    index_returns = context.inputs['index_returns']
    stage_changes = context.inputs['stage_distribution_change']
    risks = identify_risks(index_returns, stage_changes)
    return {'risks': risks}

# Function to identify risks (simplified example)
def identify_risks(index_returns, stage_changes):
    # Calculate risk levels
    risks = []
    for index in index_returns:
        risk_level = 'low' if index['avg_change_pct'] > 0 else 'high'
        risks.append(risk_level)
    return risks