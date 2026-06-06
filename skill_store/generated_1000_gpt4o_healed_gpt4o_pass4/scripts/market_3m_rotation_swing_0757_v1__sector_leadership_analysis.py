def run(context): 
  # Analyze and aggregate stage scores by sector
  return sorted(context['stage_distribution_change'], key=lambda x: x['avg_stage_score'], reverse=True)