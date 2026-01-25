# Generate Fixed HTML Report
# This script creates a properly formatted HTML report

library(dplyr)
library(RSQLite)
library(DBI)

# Load the latest analysis results
load_latest_results <- function() {
  # Find the most recent comprehensive analysis file
  report_files <- list.files(path = "../../reports", 
                           pattern = "comprehensive_nse_enhanced_.*\\.csv", 
                           full.names = TRUE)
  
  if(length(report_files) > 0) {
    # Get the most recent file
    latest_file <- report_files[order(file.info(report_files)$mtime, decreasing = TRUE)[1]]
    cat("Loading analysis data from:", latest_file, "\n")
    return(read.csv(latest_file, stringsAsFactors = FALSE))
  } else {
    stop("No analysis results found. Please run the analysis first.")
  }
}

# Generate clean HTML report
generate_clean_html_report <- function() {
  cat("Generating clean HTML report...\n")
  
  # Load results
  results <- load_latest_results()
  
  # Generate timestamp
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Create clean HTML content
  html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Analysis Report - ', timestamp, '</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #333; }
        .stat-label { color: #666; margin-top: 5px; }
        .table-container { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; }
        .positive { color: #28a745; }
        .negative { color: #dc3545; }
        .neutral { color: #6c757d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NSE Stock Analysis Report</h1>
            <p>Generated on: ', format(Sys.time(), "%Y-%m-%d %H:%M:%S"), '</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">', nrow(results), '</div>
                <div class="stat-label">Total Stocks Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(results$TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE), '</div>
                <div class="stat-label">Strong Buy Signals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(results$TRADING_SIGNAL == "BUY", na.rm = TRUE), '</div>
                <div class="stat-label">Buy Signals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1), '</div>
                <div class="stat-label">Average Technical Score</div>
            </div>
        </div>
        
        <div class="table-container">
            <h2 style="padding: 20px; margin: 0; background: #f8f9fa;">📈 Top Performing Stocks</h2>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Company</th>
                        <th>Price</th>
                        <th>Technical Score</th>
                        <th>RSI</th>
                        <th>Signal</th>
                        <th>Change 1D</th>
                    </tr>
                </thead>
                <tbody>')
  
  # Add top 20 stocks
  top_stocks <- results %>%
    arrange(desc(TECHNICAL_SCORE)) %>%
    head(20)
  
  for(i in 1:nrow(top_stocks)) {
    stock <- top_stocks[i, ]
    change_class <- ifelse(stock$CHANGE_1D > 0, "positive", ifelse(stock$CHANGE_1D < 0, "negative", "neutral"))
    
    html_content <- paste0(html_content, '
                    <tr>
                        <td><strong>', stock$SYMBOL, '</strong></td>
                        <td>', ifelse(is.na(stock$COMPANY_NAME) | stock$COMPANY_NAME == "", stock$SYMBOL, stock$COMPANY_NAME), '</td>
                        <td>₹', format(stock$CURRENT_PRICE, big.mark=","), '</td>
                        <td>', round(stock$TECHNICAL_SCORE, 1), '</td>
                        <td>', round(stock$RSI, 1), '</td>
                        <td><span style="background: ', ifelse(stock$TRADING_SIGNAL == "STRONG_BUY", "#28a745", 
                                                               ifelse(stock$TRADING_SIGNAL == "BUY", "#17a2b8", 
                                                                      ifelse(stock$TRADING_SIGNAL == "HOLD", "#ffc107", "#dc3545"))), '; color: white; padding: 4px 8px; border-radius: 4px;">', stock$TRADING_SIGNAL, '</span></td>
                        <td class="', change_class, '">', ifelse(stock$CHANGE_1D > 0, "+", ""), round(stock$CHANGE_1D, 2), '%</td>
                    </tr>')
  }
  
  html_content <- paste0(html_content, '
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>')
  
  # Save the HTML file
  output_file <- paste0("../../reports/NSE_Clean_Report_", timestamp, ".html")
  writeLines(html_content, output_file)
  
  cat("✅ Clean HTML report generated:", output_file, "\n")
  return(output_file)
}

# Run the report generation
tryCatch({
  output_file <- generate_clean_html_report()
  cat("🎉 Report generation completed successfully!\n")
  cat("📁 Output file:", output_file, "\n")
}, error = function(e) {
  cat("❌ Error generating report:", e$message, "\n")
})

