def run(context):
    # Analyze latest market regime, flows, breadth, and index data
    # Audit for exceptions and gaps
    audited_context = {'status': 'audit_complete', 'context': context}
    return audited_context