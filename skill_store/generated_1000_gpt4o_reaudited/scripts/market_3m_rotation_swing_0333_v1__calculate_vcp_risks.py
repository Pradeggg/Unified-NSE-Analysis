def run(context): 
    # Analyze VCP scores to identify potential risks 
    vcp_risks = [] 
    for record in context['score_data']: 
        if record['vcp_score'] < 50: 
            vcp_risks.append(record['symbol']) 
    return vcp_risks