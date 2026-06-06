def run(context): 
    vcp_risks = [] 
    for record in context['score_data']: 
        if record.get('vcp_score', 0) < 50: 
            vcp_risks.append(record['symbol']) 
    return vcp_risks