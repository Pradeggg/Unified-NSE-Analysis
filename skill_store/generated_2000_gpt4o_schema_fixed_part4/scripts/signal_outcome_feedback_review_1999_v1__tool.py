# The code is placeholder and assumes the context provided is correct. Implement relevant logic here.

import pandas as pd

 def run(context):
     # Load and preprocess data from context
     signal_log = pd.DataFrame(context['signals.signal_log'])
     stage_snapshots = pd.DataFrame(context['scores.stage_snapshots'])
     equity_eod = pd.DataFrame(context['market.equity_eod'])

     # Implement logic to synthesize outcome reviews
     results = 'Synthesis results placeholder'
     return results