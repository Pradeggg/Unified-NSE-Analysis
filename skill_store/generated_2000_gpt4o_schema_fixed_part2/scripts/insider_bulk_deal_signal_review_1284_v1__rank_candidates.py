def run(context):
    df = context['dataframe']
    return df.sort_values(by=['insider_score', 'stage_score'], ascending=[False, False])