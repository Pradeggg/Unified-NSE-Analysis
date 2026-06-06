def run(context):
    previous_margin = context.inputs['previous_margin']
    current_margin = context.inputs['current_margin']
    if current_margin > previous_margin:
        return {'margin_trend': 'Improving'}
    elif current_margin < previous_margin:
        return {'margin_trend': 'Declining'}
    else:
        return {'margin_trend': 'Stable'}