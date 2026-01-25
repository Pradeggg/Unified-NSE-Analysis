# Simple dashboard generation test
library(dplyr)

# Create sample data
results <- data.frame(
  TECHNICAL_SCORE = c(85.3, 75.2, 65.1),
  TRADING_SIGNAL = c("STRONG_BUY", "BUY", "HOLD"),
  stringsAsFactors = FALSE
)

# Generate HTML content using sprintf
html_content <- sprintf('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>NSE Market Analysis Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .stats-grid { display: flex; gap: 20px; }
        .stat-card { background: #f5f5f5; padding: 20px; border-radius: 8px; }
        .stat-number { font-size: 2em; font-weight: bold; color: #1976d2; }
        .stat-label { color: #666; }
    </style>
</head>
<body>
    <h1>NSE Market Analysis Dashboard</h1>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">%d</div>
            <div class="stat-label">Total Stocks Analyzed</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">%d</div>
            <div class="stat-label">Strong Buy Signals</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">%.1f</div>
            <div class="stat-label">Average Technical Score</div>
        </div>
    </div>
</body>
</html>', 
nrow(results), 
sum(results$TRADING_SIGNAL == "STRONG_BUY"), 
round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1))

# Write HTML file
writeLines(html_content, "simple_dashboard.html")
cat("Simple dashboard created successfully!\n")
cat("Variables properly interpolated:\n")
cat("- Total stocks:", nrow(results), "\n")
cat("- Strong buys:", sum(results$TRADING_SIGNAL == "STRONG_BUY"), "\n")
cat("- Avg score:", round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1), "\n")

