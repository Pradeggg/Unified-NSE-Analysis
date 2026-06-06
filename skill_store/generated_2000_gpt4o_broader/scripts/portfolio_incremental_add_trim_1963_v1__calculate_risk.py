def run(context):
    return [dict(risk_flag='High' if score < 2 else 'Low') for score in context['stage_score']]