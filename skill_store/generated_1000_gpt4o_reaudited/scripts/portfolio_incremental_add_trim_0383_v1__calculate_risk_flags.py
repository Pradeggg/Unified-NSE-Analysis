def run(context):
    snapshot_data = context.inputs['snapshot_data']
    risk_flags = snapshot_data[snapshot_data['technical_score'] < 30]['symbol'].tolist()
    return {'risk_flags': risk_flags}