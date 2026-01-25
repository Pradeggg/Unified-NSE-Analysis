# Test HTML template generation
library(dplyr)

# Create sample data
results <- data.frame(
  TECHNICAL_SCORE = c(85.3, 75.2, 65.1),
  TRADING_SIGNAL = c("STRONG_BUY", "BUY", "HOLD"),
  stringsAsFactors = FALSE
)

# Test the HTML template
html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <title>Test Dashboard</title>
</head>
<body>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number">', nrow(results), '</div>
            <div class="stat-label">Total Stocks Analyzed</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">', sum(results$TRADING_SIGNAL == "STRONG_BUY"), '</div>
            <div class="stat-label">Strong Buy Signals</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">', round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1), '</div>
            <div class="stat-label">Average Technical Score</div>
        </div>
    </div>
</body>
</html>')

# Write test file
writeLines(html_content, "test_dashboard.html")
cat("Test HTML file created successfully!\n")
cat("Content preview:\n")
cat(substr(html_content, 1, 500), "...\n")

