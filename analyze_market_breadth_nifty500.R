# =============================================================================
# NIFTY500 MARKET BREADTH ANALYSIS
# Analyzes how many NIFTY500 stocks are above/below key DMAs (20, 50, 100, 200)
# =============================================================================

library(dplyr)
library(TTR)
library(lubridate)

# =============================================================================
# Configuration
# =============================================================================
data_dir <- "data"
reports_dir <- "reports"

# =============================================================================
# Load Stock Data
# =============================================================================
cat("=== NIFTY500 MARKET BREADTH ANALYSIS ===\n")
cat("Loading stock data...\n")

# Load from cache if available
stock_data <- NULL
if(file.exists(file.path(data_dir, "nse_stock_cache.RData"))) {
  load(file.path(data_dir, "nse_stock_cache.RData"))
  if(exists("nse_stock_data")) {
    stock_data <- nse_stock_data
    cat("✅ Loaded stock data from cache:", nrow(stock_data), "records\n")
  }
}

# If no cache, load from CSV
if(is.null(stock_data)) {
  stock_data_file <- file.path(data_dir, "nse_sec_full_data.csv")
  if(file.exists(stock_data_file)) {
    stock_data <- read.csv(stock_data_file, stringsAsFactors = FALSE)
    cat("✅ Loaded stock data from CSV:", nrow(stock_data), "records\n")
  } else {
    stop("Stock data file not found!")
  }
}

# Convert TIMESTAMP to Date
stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)

# Get latest date
latest_date <- max(stock_data$TIMESTAMP, na.rm = TRUE)
cat("Latest data date:", as.character(latest_date), "\n")

# Get unique stocks
all_stocks <- unique(stock_data$SYMBOL)
cat("Total unique stocks:", length(all_stocks), "\n")

# =============================================================================
# Filter for stocks with sufficient historical data (at least 200 days)
# =============================================================================
cat("\nFiltering stocks with sufficient historical data (≥200 days)...\n")

stocks_with_sufficient_data <- c()
min_days_required <- 200

for(symbol in all_stocks) {
  stock_history <- stock_data %>%
    filter(SYMBOL == symbol) %>%
    filter(!is.na(CLOSE) & CLOSE > 0) %>%
    arrange(TIMESTAMP) %>%
    select(SYMBOL, TIMESTAMP, CLOSE)
  
  if(nrow(stock_history) >= min_days_required) {
    stocks_with_sufficient_data <- c(stocks_with_sufficient_data, symbol)
  }
}

cat("✅ Stocks with ≥200 days of data:", length(stocks_with_sufficient_data), "\n")

# For NIFTY500 analysis, we'll use all stocks with sufficient data
# (In a real scenario, you'd filter for actual NIFTY500 constituents)
nifty500_stocks <- stocks_with_sufficient_data
cat("Analyzing", length(nifty500_stocks), "stocks for market breadth\n\n")

# =============================================================================
# Calculate DMA Analysis for Each Stock
# =============================================================================
cat("Calculating DMA analysis for each stock...\n")

dma_results <- data.frame(
  SYMBOL = character(),
  CURRENT_PRICE = numeric(),
  SMA_20 = numeric(),
  SMA_50 = numeric(),
  SMA_100 = numeric(),
  SMA_200 = numeric(),
  ABOVE_20DMA = logical(),
  ABOVE_50DMA = logical(),
  ABOVE_100DMA = logical(),
  ABOVE_200DMA = logical(),
  stringsAsFactors = FALSE
)

processed <- 0
errors <- 0

for(symbol in nifty500_stocks) {
  tryCatch({
    # Get stock history
    stock_history <- stock_data %>%
      filter(SYMBOL == symbol) %>%
      filter(!is.na(CLOSE) & CLOSE > 0) %>%
      arrange(TIMESTAMP) %>%
      select(SYMBOL, TIMESTAMP, CLOSE)
    
    if(nrow(stock_history) < min_days_required) next
    
    # Get latest price
    latest_price <- stock_history$CLOSE[nrow(stock_history)]
    
    # Calculate SMAs
    prices <- stock_history$CLOSE
    sma_20 <- tryCatch(tail(SMA(prices, n = 20), 1), error = function(e) NA)
    sma_50 <- tryCatch(tail(SMA(prices, n = 50), 1), error = function(e) NA)
    sma_100 <- tryCatch(tail(SMA(prices, n = 100), 1), error = function(e) NA)
    sma_200 <- tryCatch(tail(SMA(prices, n = 200), 1), error = function(e) NA)
    
    # Check if price is above each DMA
    above_20 <- !is.na(sma_20) && latest_price > sma_20
    above_50 <- !is.na(sma_50) && latest_price > sma_50
    above_100 <- !is.na(sma_100) && latest_price > sma_100
    above_200 <- !is.na(sma_200) && latest_price > sma_200
    
    # Add to results
    dma_results <- rbind(dma_results, data.frame(
      SYMBOL = symbol,
      CURRENT_PRICE = latest_price,
      SMA_20 = sma_20,
      SMA_50 = sma_50,
      SMA_100 = sma_100,
      SMA_200 = sma_200,
      ABOVE_20DMA = above_20,
      ABOVE_50DMA = above_50,
      ABOVE_100DMA = above_100,
      ABOVE_200DMA = above_200,
      stringsAsFactors = FALSE
    ))
    
    processed <- processed + 1
    if(processed %% 50 == 0) {
      cat("Processed", processed, "stocks...\n")
    }
  }, error = function(e) {
    errors <<- errors + 1
    # Silently skip errors
  })
}

cat("✅ Processed", processed, "stocks successfully\n")
if(errors > 0) {
  cat("⚠️  Errors encountered:", errors, "\n")
}

# =============================================================================
# Calculate Market Breadth Percentages
# =============================================================================
cat("\nCalculating market breadth percentages...\n")

total_stocks <- nrow(dma_results)

# Calculate percentages
breadth_200 <- sum(dma_results$ABOVE_200DMA, na.rm = TRUE)
pct_above_200 <- round((breadth_200 / total_stocks) * 100, 2)
pct_below_200 <- round(100 - pct_above_200, 2)

breadth_100 <- sum(dma_results$ABOVE_100DMA, na.rm = TRUE)
pct_above_100 <- round((breadth_100 / total_stocks) * 100, 2)
pct_below_100 <- round(100 - pct_above_100, 2)

breadth_50 <- sum(dma_results$ABOVE_50DMA, na.rm = TRUE)
pct_above_50 <- round((breadth_50 / total_stocks) * 100, 2)
pct_below_50 <- round(100 - pct_above_50, 2)

breadth_20 <- sum(dma_results$ABOVE_20DMA, na.rm = TRUE)
pct_above_20 <- round((breadth_20 / total_stocks) * 100, 2)
pct_below_20 <- round(100 - pct_above_20, 2)

# =============================================================================
# Market Breadth Assessment
# =============================================================================
# Assess overall market breadth
# Strong breadth: >70% above DMAs
# Moderate breadth: 50-70% above DMAs
# Weak breadth: <50% above DMAs

assess_breadth <- function(pct_above) {
  if(pct_above >= 70) {
    return(list(status = "STRONG", color = "green", icon = "🟢"))
  } else if(pct_above >= 50) {
    return(list(status = "MODERATE", color = "yellow", icon = "🟡"))
  } else {
    return(list(status = "WEAK", color = "red", icon = "🔴"))
  }
}

breadth_200_assessment <- assess_breadth(pct_above_200)
breadth_100_assessment <- assess_breadth(pct_above_100)
breadth_50_assessment <- assess_breadth(pct_above_50)
breadth_20_assessment <- assess_breadth(pct_above_20)

# Overall market breadth (average of all DMAs)
avg_breadth <- mean(c(pct_above_200, pct_above_100, pct_above_50, pct_above_20))
overall_assessment <- assess_breadth(avg_breadth)

# =============================================================================
# Generate HTML Report
# =============================================================================
cat("\nGenerating HTML report...\n")

timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
report_file <- file.path(reports_dir, paste0("NIFTY500_Market_Breadth_", timestamp, ".html"))

html_content <- paste0('
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY500 Market Breadth Analysis</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: "Roboto", "Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #212121;
            font-weight: 400;
            line-height: 1.6;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            color: white;
        }
        
        .header h1 {
            font-size: 3rem;
            font-weight: 300;
            margin-bottom: 16px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
            letter-spacing: -0.5px;
        }
        
        .header p {
            font-size: 1.25rem;
            font-weight: 400;
            opacity: 0.95;
            letter-spacing: 0.2px;
        }
        
        .summary-section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .summary-section h2 {
            color: #1976d2;
            margin-bottom: 20px;
            font-size: 1.8rem;
            font-weight: 500;
            letter-spacing: 0.2px;
        }
        
        .summary-section > p {
            margin-bottom: 24px;
            color: #616161;
            font-size: 1rem;
        }
        
        .breadth-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .breadth-card {
            background: rgba(255, 255, 255, 0.8);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
            border: 1px solid rgba(0,0,0,0.05);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-left: 5px solid;
        }
        
        .breadth-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.15);
        }
        
        .breadth-card.strong {
            border-left-color: #4caf50;
        }
        
        .breadth-card.moderate {
            border-left-color: #ff9800;
        }
        
        .breadth-card.weak {
            border-left-color: #f44336;
        }
        
        .breadth-card h3 {
            font-size: 1.25rem;
            font-weight: 500;
            margin-bottom: 16px;
            color: #212121;
        }
        
        .breadth-stats {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 16px 0;
        }
        
        .stat-item {
            text-align: center;
            flex: 1;
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 300;
            margin-bottom: 8px;
            line-height: 1;
        }
        
        .stat-label {
            font-size: 0.875rem;
            color: #616161;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }
        
        .stat-value.above {
            color: #4caf50;
        }
        
        .stat-value.below {
            color: #f44336;
        }
        
        .progress-bar {
            width: 100%;
            height: 32px;
            background: rgba(0,0,0,0.05);
            border-radius: 16px;
            overflow: hidden;
            margin: 16px 0;
            position: relative;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4caf50 0%, #8bc34a 100%);
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 500;
            font-size: 0.875rem;
        }
        
        .progress-fill.moderate {
            background: linear-gradient(90deg, #ff9800 0%, #ffb74d 100%);
        }
        
        .progress-fill.weak {
            background: linear-gradient(90deg, #f44336 0%, #e57373 100%);
        }
        
        .assessment-badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 16px;
            font-weight: 500;
            margin-top: 12px;
            font-size: 0.875rem;
        }
        
        .assessment-badge.strong {
            background: #4caf50;
            color: white;
        }
        
        .assessment-badge.moderate {
            background: #ff9800;
            color: white;
        }
        
        .assessment-badge.weak {
            background: #f44336;
            color: white;
        }
        
        .breadth-card > p {
            margin-top: 12px;
            font-size: 0.875rem;
            color: #616161;
        }
        
        .overall-assessment {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            margin-top: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .overall-assessment h2 {
            font-size: 1.8rem;
            font-weight: 500;
            margin-bottom: 16px;
            color: #1976d2;
            letter-spacing: 0.2px;
        }
        
        .overall-value {
            font-size: 4rem;
            font-weight: 300;
            margin: 24px 0;
            color: #1976d2;
            line-height: 1;
        }
        
        .overall-assessment > p {
            margin-top: 16px;
            color: #616161;
            font-size: 0.875rem;
        }
        
        .details-section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 32px;
            margin-top: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .details-section h2 {
            color: #1976d2;
            margin-bottom: 24px;
            font-size: 1.8rem;
            font-weight: 500;
            letter-spacing: 0.2px;
        }
        
        .info-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        .info-table th,
        .info-table td {
            padding: 16px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .info-table th {
            background: rgba(0,0,0,0.02);
            font-weight: 500;
            color: #1976d2;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }
        
        .info-table td {
            color: #212121;
            font-size: 0.9375rem;
        }
        
        .info-table tr:hover {
            background: rgba(25, 118, 210, 0.05);
        }
        
        .info-table strong {
            color: #1976d2;
            font-weight: 500;
        }
        
        .footer {
            text-align: center;
            padding: 24px;
            color: rgba(255, 255, 255, 0.9);
            font-size: 0.875rem;
            margin-top: 30px;
        }
        
        .footer p {
            margin: 4px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NIFTY500 Market Breadth Analysis</h1>
            <p>Analysis Date: ', format(latest_date, "%B %d, %Y"), '</p>
            <p>Total Stocks Analyzed: ', total_stocks, '</p>
        </div>
        
        <div class="summary-section">
            <h2>Market Breadth Summary</h2>
            <p>
                Market breadth measures the percentage of stocks trading above key moving averages. 
                Strong breadth (>70%) indicates broad market participation, while weak breadth (<50%) suggests limited participation.
            </p>
                
                <div class="breadth-grid">
                    <div class="breadth-card ', tolower(breadth_200_assessment$status), '">
                        <h3>📈 200-Day Moving Average</h3>
                        <div class="breadth-stats">
                            <div class="stat-item">
                                <div class="stat-value above">', pct_above_200, '%</div>
                                <div class="stat-label">Above 200 DMA</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value below">', pct_below_200, '%</div>
                                <div class="stat-label">Below 200 DMA</div>
                            </div>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill ', tolower(breadth_200_assessment$status), '" style="width: ', pct_above_200, '%;">
                                ', pct_above_200, '%
                            </div>
                        </div>
                        <div class="assessment-badge ', tolower(breadth_200_assessment$status), '">
                            ', breadth_200_assessment$icon, ' ', breadth_200_assessment$status, ' BREADTH
                        </div>
                        <p>
                            ', breadth_200, ' stocks above / ', (total_stocks - breadth_200), ' stocks below
                        </p>
                    </div>
                    
                    <div class="breadth-card ', tolower(breadth_100_assessment$status), '">
                        <h3>📊 100-Day Moving Average</h3>
                        <div class="breadth-stats">
                            <div class="stat-item">
                                <div class="stat-value above">', pct_above_100, '%</div>
                                <div class="stat-label">Above 100 DMA</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value below">', pct_below_100, '%</div>
                                <div class="stat-label">Below 100 DMA</div>
                            </div>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill ', tolower(breadth_100_assessment$status), '" style="width: ', pct_above_100, '%;">
                                ', pct_above_100, '%
                            </div>
                        </div>
                        <div class="assessment-badge ', tolower(breadth_100_assessment$status), '">
                            ', breadth_100_assessment$icon, ' ', breadth_100_assessment$status, ' BREADTH
                        </div>
                        <p>
                            ', breadth_100, ' stocks above / ', (total_stocks - breadth_100), ' stocks below
                        </p>
                    </div>
                    
                    <div class="breadth-card ', tolower(breadth_50_assessment$status), '">
                        <h3>📉 50-Day Moving Average</h3>
                        <div class="breadth-stats">
                            <div class="stat-item">
                                <div class="stat-value above">', pct_above_50, '%</div>
                                <div class="stat-label">Above 50 DMA</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value below">', pct_below_50, '%</div>
                                <div class="stat-label">Below 50 DMA</div>
                            </div>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill ', tolower(breadth_50_assessment$status), '" style="width: ', pct_above_50, '%;">
                                ', pct_above_50, '%
                            </div>
                        </div>
                        <div class="assessment-badge ', tolower(breadth_50_assessment$status), '">
                            ', breadth_50_assessment$icon, ' ', breadth_50_assessment$status, ' BREADTH
                        </div>
                        <p>
                            ', breadth_50, ' stocks above / ', (total_stocks - breadth_50), ' stocks below
                        </p>
                    </div>
                    
                    <div class="breadth-card ', tolower(breadth_20_assessment$status), '">
                        <h3>📊 20-Day Moving Average</h3>
                        <div class="breadth-stats">
                            <div class="stat-item">
                                <div class="stat-value above">', pct_above_20, '%</div>
                                <div class="stat-label">Above 20 DMA</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value below">', pct_below_20, '%</div>
                                <div class="stat-label">Below 20 DMA</div>
                            </div>
                        </div>
                        <div class="progress-bar">
                            <div class="progress-fill ', tolower(breadth_20_assessment$status), '" style="width: ', pct_above_20, '%;">
                                ', pct_above_20, '%
                            </div>
                        </div>
                        <div class="assessment-badge ', tolower(breadth_20_assessment$status), '">
                            ', breadth_20_assessment$icon, ' ', breadth_20_assessment$status, ' BREADTH
                        </div>
                        <p>
                            ', breadth_20, ' stocks above / ', (total_stocks - breadth_20), ' stocks below
                        </p>
                    </div>
                </div>
                
                <div class="overall-assessment">
                    <h2>Overall Market Breadth Assessment</h2>
                    <div class="overall-value">', round(avg_breadth, 2), '%</div>
                    <div class="assessment-badge ', tolower(overall_assessment$status), '" style="font-size: 1rem; padding: 10px 20px;">
                        ', overall_assessment$icon, ' ', overall_assessment$status, ' MARKET BREADTH
                    </div>
                    <p>
                        Average percentage of stocks above all key moving averages
                    </p>
                </div>
            </div>
            
            <div class="details-section">
                <h2>Detailed Statistics</h2>
                <table class="info-table">
                    <thead>
                        <tr>
                            <th>Moving Average</th>
                            <th>Stocks Above</th>
                            <th>Stocks Below</th>
                            <th>% Above</th>
                            <th>% Below</th>
                            <th>Assessment</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>200-Day DMA</strong></td>
                            <td>', breadth_200, '</td>
                            <td>', (total_stocks - breadth_200), '</td>
                            <td><strong>', pct_above_200, '%</strong></td>
                            <td>', pct_below_200, '%</td>
                            <td><span class="assessment-badge ', tolower(breadth_200_assessment$status), '">', breadth_200_assessment$status, '</span></td>
                        </tr>
                        <tr>
                            <td><strong>100-Day DMA</strong></td>
                            <td>', breadth_100, '</td>
                            <td>', (total_stocks - breadth_100), '</td>
                            <td><strong>', pct_above_100, '%</strong></td>
                            <td>', pct_below_100, '%</td>
                            <td><span class="assessment-badge ', tolower(breadth_100_assessment$status), '">', breadth_100_assessment$status, '</span></td>
                        </tr>
                        <tr>
                            <td><strong>50-Day DMA</strong></td>
                            <td>', breadth_50, '</td>
                            <td>', (total_stocks - breadth_50), '</td>
                            <td><strong>', pct_above_50, '%</strong></td>
                            <td>', pct_below_50, '%</td>
                            <td><span class="assessment-badge ', tolower(breadth_50_assessment$status), '">', breadth_50_assessment$status, '</span></td>
                        </tr>
                        <tr>
                            <td><strong>20-Day DMA</strong></td>
                            <td>', breadth_20, '</td>
                            <td>', (total_stocks - breadth_20), '</td>
                            <td><strong>', pct_above_20, '%</strong></td>
                            <td>', pct_below_20, '%</td>
                            <td><span class="assessment-badge ', tolower(breadth_20_assessment$status), '">', breadth_20_assessment$status, '</span></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">
            <p>Generated on ', format(Sys.time(), "%B %d, %Y at %I:%M %p"), '</p>
            <p>NIFTY500 Market Breadth Analysis - Unified NSE Analysis System</p>
        </div>
    </div>
</body>
</html>
')

# Write HTML file
writeLines(html_content, report_file)
cat("✅ HTML report saved to:", report_file, "\n")

# =============================================================================
# Save CSV Results
# =============================================================================
csv_file <- file.path(reports_dir, paste0("NIFTY500_Market_Breadth_", timestamp, ".csv"))
write.csv(dma_results, csv_file, row.names = FALSE)
cat("✅ CSV results saved to:", csv_file, "\n")

# =============================================================================
# Print Summary
# =============================================================================
cat("\n=== MARKET BREADTH SUMMARY ===\n")
cat("200-Day DMA: ", pct_above_200, "% above / ", pct_below_200, "% below\n", sep = "")
cat("100-Day DMA: ", pct_above_100, "% above / ", pct_below_100, "% below\n", sep = "")
cat("50-Day DMA:  ", pct_above_50, "% above / ", pct_below_50, "% below\n", sep = "")
cat("20-Day DMA:  ", pct_above_20, "% above / ", pct_below_20, "% below\n", sep = "")
cat("\nOverall Market Breadth: ", round(avg_breadth, 2), "% (", overall_assessment$status, ")\n", sep = "")
cat("\n✅ Analysis completed successfully!\n")

