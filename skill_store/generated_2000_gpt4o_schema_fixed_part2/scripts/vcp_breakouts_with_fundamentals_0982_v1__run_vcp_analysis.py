# Sample code to merge VCP and fundamental analysis results
import pandas as pd
def run(context):
    vcp_df = pd.DataFrame(context['vcp_data'])
    fundamentals_df = pd.DataFrame(context['fundamental_data'])
    combined_df = pd.merge(vcp_df, fundamentals_df, on='symbol')
    return combined_df.sort_values(by='vcp_score', ascending=False).head(20).to_dict('records')