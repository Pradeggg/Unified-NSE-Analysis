#!/usr/bin/env Rscript
# Analyze top stocks for all NSE indexes
# Show top 5 by each index, ordered by index strength

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(jsonlite)
})

cat("=== ANALYZING TOP STOCKS FOR ALL NSE INDEXES ===\n\n")

# Set working directory
setwd("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis")

# Load latest comprehensive analysis results
analysis_files <- list.files("reports", pattern = "comprehensive_nse_enhanced_.*\\.csv", full.names = TRUE)
if (length(analysis_files) == 0) {
  stop("No comprehensive analysis results found. Please run the main analysis pipeline first.")
}
latest_analysis_file <- analysis_files[order(file.info(analysis_files)$mtime, decreasing = TRUE)[1]]
cat("Loading analysis results from:", basename(latest_analysis_file), "\n\n")

all_stocks_analysis <- read_csv(latest_analysis_file, show_col_types = FALSE)
cat("Total stocks analyzed:", nrow(all_stocks_analysis), "\n\n")

# Define index performance data (1M, 3M, 6M percentages)
index_performance <- list(
  "Nifty Metal" = list(perf1M = 6.3, perf3M = 15.6, perf6M = 27.3),
  "Nifty Auto" = list(perf1M = 0.2, perf3M = 13.4, perf6M = 18.3),
  "Nifty Midcap 50" = list(perf1M = 6.0, perf3M = 5.2, perf6M = 12.9),
  "Nifty 200" = list(perf1M = 4.2, perf3M = 4.5, perf6M = 8.4),
  "Nifty 100" = list(perf1M = 4.0, perf3M = 4.5, perf6M = 7.5),
  "Nifty 50" = list(perf1M = 4.2, perf3M = 4.5, perf6M = 6.6),
  "Nifty Next 50" = list(perf1M = 2.9, perf3M = 4.5, perf6M = 11.7),
  "Nifty Realty" = list(perf1M = 8.4, perf3M = 4.2, perf6M = 12.7),
  "Nifty 500" = list(perf1M = 4.0, perf3M = 4.0, perf6M = 9.2),
  "Nifty Bank" = list(perf1M = 4.8, perf3M = 3.7, perf6M = 6.7),
  "Nifty Energy" = list(perf1M = 3.5, perf3M = 3.6, perf6M = 8.5),
  "NIFTY SMLCAP 100" = list(perf1M = 4.0, perf3M = 2.8, perf6M = 14.1),
  "NIFTY SMLCAP 50" = list(perf1M = 4.8, perf3M = 2.4, perf6M = 13.9),
  "Nifty IT" = list(perf1M = 5.9, perf3M = 1.7, perf6M = -0.3),
  "NIFTY SMLCAP 250" = list(perf1M = 3.2, perf3M = 1.6, perf6M = 14.7),
  "Nifty FMCG" = list(perf1M = 2.3, perf3M = 0.9, perf6M = 0.6),
  "Nifty Pharma" = list(perf1M = 2.6, perf3M = -2.1, perf6M = 5.6),
  "Nifty Media" = list(perf1M = -2.8, perf3M = NA, perf6M = NA)
)

# Define all major NSE indexes with their constituent stocks
index_constituents <- list(
  "Nifty 50" = c("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN", 
                 "BHARTIARTL", "KOTAKBANK", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA", 
                 "TATAMOTORS", "WIPRO", "ULTRACEMCO", "TITAN", "BAJFINANCE", "NESTLEIND", "LT",
                 "HCLTECH", "ICICIPRULI", "ADANIENT", "ONGC", "POWERGRID", "TATACONSUM", "COALINDIA",
                 "NTPC", "HDFCLIFE", "INDUSINDBK", "TECHM", "ADANIPORTS", "M&M", "JSWSTEEL", 
                 "BAJAJFINSV", "DIVISLAB", "GRASIM", "TATASTEEL", "HINDALCO", "CIPLA", "DRREDDY",
                 "EICHERMOT", "BRITANNIA", "HEROMOTOCO", "BPCL", "MARICO", "APOLLOHOSP", "ADANIPOWER"),
  
  "Nifty Bank" = c("HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK", 
                   "FEDERALBNK", "IDFCFIRSTB", "PNB", "BANKBARODA", "UNIONBANK", "CANBK", "IOB"),
  
  "Nifty IT" = c("TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "LTTS", "MPHASIS", "COFORGE", 
                 "MINDTREE", "ZENSAR", "SONATA", "HEXAWARE", "RAMSARUP"),
  
  "Nifty Auto" = c("MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "ASHOKLEY", 
                   "M&M", "TVSMOTOR", "MRF", "APOLLOTYRE", "BALKRISIND", "BHARATFORG", "MOTHERSON"),
  
  "Nifty Pharma" = c("SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "BIOCON", 
                     "TORNTPHARM", "ALKEM", "LUPIN", "AUROPHARMA", "GLENMARK", "CADILAHC", "ZYDUS"),
  
  "Nifty FMCG" = c("HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO", "COLPAL", 
                   "GODREJCP", "UBL", "VBL", "TATACONSUM", "EMAMILTD", "RADICO"),
  
  "Nifty Metal" = c("TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "HINDCOPPER", 
                   "NATIONALUM", "SAIL", "WELCORP", "JINDALSTEL", "NALCO", "MOIL"),
  
  "Nifty Energy" = c("RELIANCE", "ONGC", "NTPC", "POWERGRID", "BPCL", "IOC", "HPCL", "ADANIGREEN",
                     "ADANIPOWER", "TORNTPOWER", "TATAPOWER", "NHPC", "GAIL"),
  
  "Nifty Realty" = c("DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "BRIGADE", "SOBHA", "SUNTECK",
                     "LODHA", "MACROTECH", "PURAVANKARA", "KOLTEPATIL", "MAHINDRA"),
  
  "Nifty Consumer Durables" = c("TITAN", "WHIRLPOOL", "VOLTAS", "BLUESTARCO", "ORIENTELEC", 
                                "CROMPTON", "TTKPRESTIG", "RAJESH", "ORIENTREF", "BUTTERFLY"),
  
  "Nifty Infrastructure" = c("LT", "ADANIPORTS", "ADANIGREEN", "ADANIPOWER", "NTPC", "POWERGRID",
                              "BHEL", "SIEMENS", "ABB", "CONCOR", "IRBINFRA", "GMRINFRA", "RELINFRA"),
  
  "Nifty Media" = c("ZEEL", "NETWORK18", "TVTODAY", "HTMEDIA", "JAGRAN", "DB", "TV18BRDCST"),
  
  "Nifty PSU Bank" = c("SBIN", "PNB", "BANKBARODA", "UNIONBANK", "CANBK", "IOB", "CENTRALBK",
                        "INDIANB", "UCOBANK", "PSB"),
  
  "Nifty Private Bank" = c("HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
                           "FEDERALBNK", "IDFCFIRSTB", "RBLBANK", "YESBANK", "BANDHANBNK"),
  
  "Nifty Oil & Gas" = c("RELIANCE", "ONGC", "IOC", "BPCL", "HPCL", "GAIL", "OIL", "PETRONET",
                         "MRPL", "ADANITRANS"),
  
  "Nifty 100" = c("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
                  "BHARTIARTL", "KOTAKBANK", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
                  "TATAMOTORS", "WIPRO", "ULTRACEMCO", "TITAN", "BAJFINANCE", "NESTLEIND", "LT"),
  
  "Nifty Next 50" = c("ADANIPORTS", "ADANIENT", "ADANIGREEN", "ADANIPOWER", "BAJAJFINSV",
                     "DIVISLAB", "HDFCLIFE", "ICICIPRULI", "INDUSINDBK", "MARICO", "M&M",
                     "NTPC", "POWERGRID", "TATACONSUM", "VEDL"),
  
  "Nifty 200" = c("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
                 "BHARTIARTL", "KOTAKBANK", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
                 "TATAMOTORS", "WIPRO", "ULTRACEMCO", "TITAN", "BAJFINANCE", "NESTLEIND", "LT",
                 "ADANIPORTS", "ADANIENT", "ADANIGREEN", "ADANIPOWER", "BAJAJFINSV", "DIVISLAB"),
  
  "Nifty 500" = c("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN",
                 "BHARTIARTL", "KOTAKBANK", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
                 "TATAMOTORS", "WIPRO", "ULTRACEMCO", "TITAN", "BAJFINANCE", "NESTLEIND", "LT",
                 "ADANIPORTS", "ADANIENT", "ADANIGREEN", "ADANIPOWER", "BAJAJFINSV", "DIVISLAB",
                 "JSWSTEEL", "HDFCLIFE", "INDUSINDBK", "TECHM", "M&M", "TATASTEEL", "HINDALCO"),
  
  "Nifty Midcap 50" = c("ADANIPORTS", "ADANIENT", "ADANIGREEN", "BAJAJFINSV", "DIVISLAB",
                       "HDFCLIFE", "ICICIPRULI", "INDUSINDBK", "MARICO", "M&M", "NTPC",
                       "POWERGRID", "TATACONSUM", "VEDL", "AUROPHARMA", "BIOCON", "CIPLA"),
  
  "NIFTY SMLCAP 100" = c("ADANIGREEN", "ADANIPOWER", "ADANIENSOL", "AUROPHARMA", "BIOCON",
                        "CIPLA", "DIVISLAB", "ICICIPRULI", "INDUSINDBK", "MARICO"),
  
  "NIFTY SMLCAP 50" = c("ADANIGREEN", "ADANIPOWER", "ADANIENSOL", "AUROPHARMA", "BIOCON",
                       "CIPLA", "DIVISLAB", "ICICIPRULI", "INDUSINDBK", "MARICO"),
  
  "NIFTY SMLCAP 250" = c("ADANIGREEN", "ADANIPOWER", "ADANIENSOL", "AUROPHARMA", "BIOCON",
                        "CIPLA", "DIVISLAB", "ICICIPRULI", "INDUSINDBK", "MARICO", "EICHERMOT")
)

# Function to analyze stocks for an index
analyze_index <- function(index_name, constituents, all_stocks) {
  # Filter stocks that belong to this index
  index_stocks <- all_stocks %>%
    filter(SYMBOL %in% constituents) %>%
    arrange(desc(TECHNICAL_SCORE)) %>%
    head(5)
  
  if(nrow(index_stocks) == 0) {
    return(NULL)
  }
  
  # Calculate index strength (average technical score of top 5)
  index_strength <- mean(index_stocks$TECHNICAL_SCORE, na.rm = TRUE)
  
  return(list(
    index_name = index_name,
    index_strength = index_strength,
    stocks = index_stocks
  ))
}

# Analyze all indexes
cat("Analyzing stocks for", length(index_constituents), "indexes...\n\n")
index_results <- list()

for(index_name in names(index_constituents)) {
  constituents <- index_constituents[[index_name]]
  result <- analyze_index(index_name, constituents, all_stocks_analysis)
  if(!is.null(result)) {
    index_results[[index_name]] <- result
  }
}

# Sort indexes by strength (descending)
sorted_indexes <- names(index_results)[order(sapply(index_results, function(x) x$index_strength), decreasing = TRUE)]

cat("═══════════════════════════════════════════════════════════════\n")
cat("INDEXES RANKED BY STRENGTH (Top 5 Stocks Each)\n")
cat("═══════════════════════════════════════════════════════════════\n\n")

# Print results for each index
for(index_name in sorted_indexes) {
  result <- index_results[[index_name]]
  cat(sprintf("\n📊 %s (Strength: %.1f)\n", index_name, result$index_strength))
  cat(rep("─", 60), "\n")
  
  stocks_df <- result$stocks %>%
    select(SYMBOL, MARKET_CAP_CATEGORY, CURRENT_PRICE, CHANGE_1D, CHANGE_1W, CHANGE_1M,
           TECHNICAL_SCORE, RELATIVE_STRENGTH, TRADING_SIGNAL, TREND_SIGNAL)
  
  print(stocks_df)
  cat("\n")
}

# Prepare data for HTML report
all_index_data <- list()
for(index_name in sorted_indexes) {
  all_index_data[[index_name]] <- index_results[[index_name]]
}

# Generate HTML report
generate_html_report <- function(index_data, output_dir = "reports") {
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  html_file <- file.path(output_dir, paste0("All_Indexes_Analysis_Report_", timestamp, ".html"))
  
  # Helper function to format stock list for an index (with clickable items)
  format_index_list <- function(stocks_df, index_name) {
    if(nrow(stocks_df) == 0) {
      return('<div class="no-data">No stocks found for this index.</div>')
    }
    
    html <- '<div class="screener-list">'
    for(i in 1:nrow(stocks_df)) {
      row <- stocks_df[i, ]
      signal_color <- switch(row$TRADING_SIGNAL,
                            "STRONG_BUY" = "#28a745",
                            "BUY" = "#5cb85c",
                            "HOLD" = "#ffc107",
                            "WEAK_HOLD" = "#ff9800",
                            "SELL" = "#dc3545",
                            "#6c757d")
      
      html <- paste0(html, '<div class="screener-item" onclick="showStockDetails(\'', row$SYMBOL, '\', ', i - 1, ')" style="cursor: pointer;">
        <div class="stock-info">
            <span class="stock-symbol">', row$SYMBOL, '</span>
            <span class="stock-price">₹', sprintf("%.2f", row$CURRENT_PRICE), ' | ', row$MARKET_CAP_CATEGORY, '</span>
        </div>
        <div class="metric-value score">', sprintf("%.1f", row$TECHNICAL_SCORE), '</div>
        <div class="metric-value" style="background: ', signal_color, '; color: white;">', row$TRADING_SIGNAL, '</div>
      </div>')
    }
    html <- paste0(html, '</div>')
    return(html)
  }
  
  # Get analysis date
  analysis_date <- format(Sys.Date(), "%B %d, %Y")
  
  # Build HTML content
  html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>All NSE Indexes Analysis Report</title>
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
        }

        .container {
            max-width: 100%;
            margin: 0 auto;
            padding: 20px;
            width: 100%;
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
            opacity: 0.9;
        }

        .index-section {
            margin: 2rem 0;
            padding: 2rem;
            background: #f8f9fa;
            border-radius: 12px;
        }

        .section-header {
            margin-bottom: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .section-header h2 {
            font-size: 2rem;
            font-weight: 400;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }

        .strength-badge {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-size: 1.2rem;
            font-weight: 500;
        }

        .section-header p {
            color: #7f8c8d;
            font-size: 1rem;
        }

        .screeners-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-top: 1.5rem;
        }

        .screener-card {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .screener-header h3 {
            color: #2c3e50;
            margin-bottom: 0.5rem;
            font-size: 1.2rem;
            font-weight: 500;
        }

        .screener-header p {
            color: #7f8c8d;
            font-size: 0.9rem;
        }

        .screener-list {
            margin-top: 1rem;
        }

        .screener-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid #ecf0f1;
            transition: background-color 0.2s;
        }

        .screener-item:hover {
            background-color: #f8f9fa;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
            margin-left: -0.5rem;
            margin-right: -0.5rem;
            border-radius: 4px;
        }

        .screener-item:last-child {
            border-bottom: none;
        }

        .stock-info {
            display: flex;
            flex-direction: column;
            flex: 1;
        }

        .stock-symbol {
            font-weight: 600;
            color: #2c3e50;
            font-size: 1rem;
        }

        .stock-price {
            font-size: 0.85rem;
            color: #7f8c8d;
            margin-top: 0.25rem;
        }

        .metric-value {
            font-weight: 600;
            padding: 0.35rem 0.75rem;
            border-radius: 4px;
            font-size: 0.9rem;
            margin-left: 0.5rem;
        }

        .metric-value.score {
            background: #e3f2fd;
            color: #1976d2;
        }

        .no-data {
            text-align: center;
            color: #7f8c8d;
            font-style: italic;
            padding: 2rem;
        }

        .performance-metrics {
            margin-top: 1rem;
        }

        .perf-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid rgba(102, 126, 234, 0.2);
        }

        .perf-item:last-child {
            border-bottom: none;
        }

        .perf-label {
            font-size: 0.95rem;
            color: #2c3e50;
            font-weight: 500;
        }

        .perf-value {
            font-size: 1.1rem;
            font-weight: 600;
        }

        .perf-value.positive {
            color: #4caf50;
        }

        .perf-value.negative {
            color: #f44336;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .summary-card {
            background: white;
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }

        .summary-card .number {
            font-size: 2rem;
            font-weight: 300;
            color: #764ba2;
            margin: 0.5rem 0;
        }

        .summary-card p {
            color: #7f8c8d;
            font-size: 0.9rem;
        }

        /* Modal Styles */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            backdrop-filter: blur(5px);
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal-content {
            background: white;
            border-radius: 16px;
            padding: 32px;
            max-width: 800px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.25);
            transform: scale(0.7);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }

        .modal-overlay.active .modal-content {
            transform: scale(1);
            opacity: 1;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 2px solid #f0f0f0;
        }

        .modal-title {
            font-size: 1.75rem;
            font-weight: 500;
            color: #667eea;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #666;
            padding: 8px;
            border-radius: 50%;
            transition: all 0.2s ease;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-close:hover {
            background: #f0f0f0;
            color: #333;
        }

        .detail-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            padding: 20px;
            background: rgba(102, 126, 234, 0.04);
            border-radius: 12px;
            border-left: 4px solid #667eea;
            margin-bottom: 16px;
        }

        .detail-item {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .detail-label {
            font-size: 0.75rem;
            color: rgba(0,0,0,0.6);
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 500;
        }

        .detail-value {
            font-size: 1.125rem;
            font-weight: 500;
            color: #2c3e50;
        }

        .detail-value.positive { color: #4caf50; }
        .detail-value.negative { color: #f44336; }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-top: 20px;
        }

        .metric-card {
            background: rgba(102, 126, 234, 0.1);
            padding: 16px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid rgba(102, 126, 234, 0.2);
        }

        .metric-card-value {
            font-size: 1.25rem;
            font-weight: 500;
            color: #667eea;
            margin-bottom: 4px;
        }

        .metric-card-label {
            font-size: 0.75rem;
            color: rgba(0,0,0,0.6);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .insight-box {
            background: rgba(76, 175, 80, 0.05);
            padding: 20px;
            border-radius: 12px;
            border-left: 4px solid #4caf50;
            margin-top: 20px;
        }

        .insight-title {
            font-size: 1.125rem;
            color: #4caf50;
            font-weight: 600;
            margin-bottom: 12px;
        }

        .insight-text {
            color: rgba(0,0,0,0.7);
            font-size: 0.95rem;
            line-height: 1.5;
        }

        @media (max-width: 768px) {
            .screeners-grid {
                grid-template-columns: 1fr;
            }

            .summary-grid {
                grid-template-columns: 1fr;
            }

            .section-header {
                flex-direction: column;
                align-items: flex-start;
            }

            .detail-row {
                grid-template-columns: 1fr;
            }

            .modal-content {
                width: 95%;
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 All NSE Indexes Analysis</h1>
            <p>Top 5 Stocks by Each Index, Ordered by Index Strength</p>
            <p style="margin-top: 10px; font-size: 1rem; opacity: 0.8;">Analysis Date: ', analysis_date, '</p>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <div class="number">', length(index_data), '</div>
                <p>Indexes Analyzed</p>
            </div>
            <div class="summary-card">
                <div class="number">', length(index_data) * 5, '</div>
                <p>Total Stocks</p>
            </div>
            <div class="summary-card">
                <div class="number">', sprintf("%.1f", max(sapply(index_data, function(x) x$index_strength))), '</div>
                <p>Strongest Index Score</p>
            </div>
        </div>')
  
  # Add each index section
  for(index_name in names(index_data)) {
    index_info <- index_data[[index_name]]
    stocks_html <- format_index_list(index_info$stocks, index_name)
    
    # Get performance data for this index
    perf_data <- index_performance[[index_name]]
    if(is.null(perf_data)) {
      perf1M <- NA
      perf3M <- NA
      perf6M <- NA
    } else {
      perf1M <- perf_data$perf1M
      perf3M <- perf_data$perf3M
      perf6M <- perf_data$perf6M
    }
    
    # Format performance metrics HTML
    # Determine color classes for each metric
    perf1M_class <- ifelse(is.na(perf1M), '', ifelse(perf1M >= 0, 'positive', 'negative'))
    perf3M_class <- ifelse(is.na(perf3M), '', ifelse(perf3M >= 0, 'positive', 'negative'))
    perf6M_class <- ifelse(is.na(perf6M), '', ifelse(perf6M >= 0, 'positive', 'negative'))
    
    # Format values
    perf1M_val <- ifelse(is.na(perf1M), 'N/A', paste0(sprintf('%.1f', perf1M), '%'))
    perf3M_val <- ifelse(is.na(perf3M), 'N/A', paste0(sprintf('%.1f', perf3M), '%'))
    perf6M_val <- ifelse(is.na(perf6M), 'N/A', paste0(sprintf('%.1f', perf6M), '%'))
    
    perf_html <- paste0('<div class="screener-card" style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);">
                    <div class="screener-header">
                        <h3>📈 Index Performance</h3>
                        <p>Returns over different periods</p>
                    </div>
                    <div class="performance-metrics">
                        <div class="perf-item">
                            <span class="perf-label">1M:</span>
                            <span class="perf-value ', perf1M_class, '">', perf1M_val, '</span>
                        </div>
                        <div class="perf-item">
                            <span class="perf-label">3M:</span>
                            <span class="perf-value ', perf3M_class, '">', perf3M_val, '</span>
                        </div>
                        <div class="perf-item">
                            <span class="perf-label">6M:</span>
                            <span class="perf-value ', perf6M_class, '">', perf6M_val, '</span>
                        </div>
                    </div>
                  </div>')
    
    html_content <- paste0(html_content, '
        <div class="index-section">
            <div class="section-header">
                <div>
                    <h2>📊 ', index_name, '</h2>
                    <p>Top 5 stocks by Technical Score</p>
                </div>
                <div class="strength-badge">Strength: ', sprintf("%.1f", index_info$index_strength), '</div>
            </div>
            <div class="screeners-grid">
                ', perf_html, '
                <div class="screener-card">
                    <div class="screener-header">
                        <h3>💪 Top 5 Stocks</h3>
                        <p>Ranked by Technical Score</p>
                    </div>
                    ', stocks_html, '
                </div>
            </div>
        </div>')
  }
  
  # Prepare all stock data for JavaScript
  all_stocks_js <- list()
  stock_counter <- 0
  for(index_name in names(index_data)) {
    index_info <- index_data[[index_name]]
    for(i in 1:nrow(index_info$stocks)) {
      row <- index_info$stocks[i, ]
      stock_counter <- stock_counter + 1
      all_stocks_js[[stock_counter]] <- list(
        symbol = row$SYMBOL,
        company_name = ifelse(is.na(row$COMPANY_NAME) || row$COMPANY_NAME == "", row$SYMBOL, row$COMPANY_NAME),
        index = index_name,
        market_cap = row$MARKET_CAP_CATEGORY,
        current_price = row$CURRENT_PRICE,
        change_1d = row$CHANGE_1D,
        change_1w = row$CHANGE_1W,
        change_1m = row$CHANGE_1M,
        technical_score = row$TECHNICAL_SCORE,
        rsi = ifelse(is.na(row$RSI), 0, row$RSI),
        relative_strength = ifelse(is.na(row$RELATIVE_STRENGTH), 0, row$RELATIVE_STRENGTH),
        can_slim_score = ifelse(is.na(row$CAN_SLIM_SCORE), 0, row$CAN_SLIM_SCORE),
        minervini_score = ifelse(is.na(row$MINERVINI_SCORE), 0, row$MINERVINI_SCORE),
        fundamental_score = ifelse(is.na(row$FUNDAMENTAL_SCORE), 0, row$FUNDAMENTAL_SCORE),
        enhanced_fund_score = ifelse(is.na(row$ENHANCED_FUND_SCORE), 0, row$ENHANCED_FUND_SCORE),
        earnings_quality = ifelse(is.na(row$EARNINGS_QUALITY), 0, row$EARNINGS_QUALITY),
        sales_growth = ifelse(is.na(row$SALES_GROWTH), 0, row$SALES_GROWTH),
        financial_strength = ifelse(is.na(row$FINANCIAL_STRENGTH), 0, row$FINANCIAL_STRENGTH),
        institutional_backing = ifelse(is.na(row$INSTITUTIONAL_BACKING), 0, row$INSTITUTIONAL_BACKING),
        trading_value = ifelse(is.na(row$TRADING_VALUE), 0, row$TRADING_VALUE),
        trading_signal = row$TRADING_SIGNAL,
        trend_signal = row$TREND_SIGNAL,
        rank = row$RANK
      )
    }
  }
  
  stocks_json <- toJSON(all_stocks_js, auto_unbox = TRUE)
  
  html_content <- paste0(html_content, '
    </div>
    
    <!-- Stock Details Modal -->
    <div class="modal-overlay" id="stockModal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalStockSymbol">Stock Details</div>
                <button class="modal-close" onclick="closeModal()">×</button>
            </div>
            <div id="modalStockDetails">
                <!-- Stock details will be populated here -->
            </div>
        </div>
    </div>
    
    <script>
        // All stocks data
        const allStocksData = ', stocks_json, ';
        
        // Function to find stock by symbol
        function findStockBySymbol(symbol) {
            return allStocksData.find(s => s.symbol === symbol);
        }
        
        // Function to show stock details
        function showStockDetails(symbol, index) {
            const stock = findStockBySymbol(symbol);
            if (!stock) return;
            
            const modal = document.getElementById("stockModal");
            const modalSymbol = document.getElementById("modalStockSymbol");
            const modalDetails = document.getElementById("modalStockDetails");
            
            modalSymbol.textContent = `${stock.symbol} - ${stock.company_name}`;
            
            // Determine performance category
            let performanceCategory = "Moderate";
            let performanceColor = "#ffc107";
            if (stock.technical_score >= 70) {
                performanceCategory = "Excellent";
                performanceColor = "#4caf50";
            } else if (stock.technical_score >= 50) {
                performanceCategory = "Good";
                performanceColor = "#8bc34a";
            } else if (stock.technical_score < 30) {
                performanceCategory = "Poor";
                performanceColor = "#f44336";
            }
            
            // Determine signal color
            let signalColor = "#6c757d";
            switch(stock.trading_signal) {
                case "STRONG_BUY": signalColor = "#28a745"; break;
                case "BUY": signalColor = "#5cb85c"; break;
                case "HOLD": signalColor = "#ffc107"; break;
                case "WEAK_HOLD": signalColor = "#ff9800"; break;
                case "SELL": signalColor = "#dc3545"; break;
            }
            
            // Determine trend color
            let trendColor = "#6c757d";
            switch(stock.trend_signal) {
                case "STRONG_BULLISH": trendColor = "#4caf50"; break;
                case "BULLISH": trendColor = "#8bc34a"; break;
                case "NEUTRAL": trendColor = "#ffc107"; break;
                case "BEARISH": trendColor = "#ff9800"; break;
                case "STRONG_BEARISH": trendColor = "#f44336"; break;
            }
            
            const detailsHTML = `
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Index</div>
                        <div class="detail-value">${stock.index}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Market Cap</div>
                        <div class="detail-value">${stock.market_cap.replace("_", " ")}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Current Price</div>
                        <div class="detail-value">₹${stock.current_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Rank</div>
                        <div class="detail-value">#${stock.rank || "N/A"}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">1 Day Change</div>
                        <div class="detail-value ${stock.change_1d >= 0 ? "positive" : "negative"}">${stock.change_1d >= 0 ? "+" : ""}${stock.change_1d.toFixed(2)}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">1 Week Change</div>
                        <div class="detail-value ${stock.change_1w >= 0 ? "positive" : "negative"}">${stock.change_1w >= 0 ? "+" : ""}${stock.change_1w.toFixed(2)}%</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">1 Month Change</div>
                        <div class="detail-value ${stock.change_1m >= 0 ? "positive" : "negative"}">${stock.change_1m >= 0 ? "+" : ""}${stock.change_1m.toFixed(2)}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">RSI</div>
                        <div class="detail-value">${stock.rsi.toFixed(1)}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Technical Score</div>
                        <div class="detail-value">${stock.technical_score.toFixed(1)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Relative Strength</div>
                        <div class="detail-value ${stock.relative_strength >= 0 ? "positive" : "negative"}">${stock.relative_strength >= 0 ? "+" : ""}${stock.relative_strength.toFixed(2)}%</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">CAN SLIM Score</div>
                        <div class="detail-value">${stock.can_slim_score}/20</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Minervini Score</div>
                        <div class="detail-value">${stock.minervini_score}/20</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Fundamental Score</div>
                        <div class="detail-value">${stock.fundamental_score.toFixed(1)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Enhanced Fund Score</div>
                        <div class="detail-value">${stock.enhanced_fund_score.toFixed(1)}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Trading Signal</div>
                        <div class="detail-value" style="background: ${signalColor}; color: white; padding: 8px 16px; border-radius: 8px; display: inline-block;">${stock.trading_signal.replace("_", " ")}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Trend Signal</div>
                        <div class="detail-value" style="background: ${trendColor}; color: white; padding: 8px 16px; border-radius: 8px; display: inline-block;">${stock.trend_signal.replace("_", " ")}</div>
                    </div>
                </div>
                
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-card-value">${stock.earnings_quality.toFixed(1)}</div>
                        <div class="metric-card-label">Earnings Quality</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value ${stock.sales_growth >= 0 ? "positive" : "negative"}">${stock.sales_growth >= 0 ? "+" : ""}${stock.sales_growth.toFixed(1)}%</div>
                        <div class="metric-card-label">Sales Growth</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value">${stock.financial_strength.toFixed(1)}</div>
                        <div class="metric-card-label">Financial Strength</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value">${stock.institutional_backing.toFixed(1)}</div>
                        <div class="metric-card-label">Institutional Backing</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-value">₹${(stock.trading_value / 1000000).toFixed(2)}M</div>
                        <div class="metric-card-label">Trading Value</div>
                    </div>
                    <div class="metric-card" style="background: ${performanceColor === "#4caf50" ? "rgba(76, 175, 80, 0.1)" : performanceColor === "#8bc34a" ? "rgba(139, 195, 74, 0.1)" : performanceColor === "#ffc107" ? "rgba(255, 193, 7, 0.1)" : "rgba(244, 67, 54, 0.1)"}; border-color: ${performanceColor};">
                        <div class="metric-card-value" style="color: ${performanceColor};">${performanceCategory}</div>
                        <div class="metric-card-label">Performance</div>
                    </div>
                </div>
                
                <div class="insight-box">
                    <div class="insight-title">💡 Investment Insight</div>
                    <div class="insight-text">
                        ${stock.technical_score >= 70 ? 
                            `This stock shows strong technical strength (${stock.technical_score.toFixed(1)}/100) with ${stock.trading_signal.replace("_", " ")} signal. The CAN SLIM score of ${stock.can_slim_score}/20 and Minervini score of ${stock.minervini_score}/20 indicate ${stock.can_slim_score >= 12 && stock.minervini_score >= 12 ? "strong" : "moderate"} fundamental alignment. Consider for ${stock.market_cap === "LARGE_CAP" ? "core" : "growth"} portfolio allocation.` :
                            stock.technical_score >= 50 ?
                            `This stock shows moderate technical strength (${stock.technical_score.toFixed(1)}/100) with ${stock.trading_signal.replace("_", " ")} signal. Monitor for improvement or consider smaller position sizes.` :
                            `This stock shows weak technical strength (${stock.technical_score.toFixed(1)}/100) with ${stock.trading_signal.replace("_", " ")} signal. High risk - consider avoiding or very small position sizes.`
                        }
                    </div>
                </div>
            `;
            
            modalDetails.innerHTML = detailsHTML;
            modal.classList.add("active");
            
            modal.addEventListener("click", function(e) {
                if (e.target === modal) {
                    closeModal();
                }
            });
            
            document.addEventListener("keydown", function(e) {
                if (e.key === "Escape" && modal.classList.contains("active")) {
                    closeModal();
                }
            });
        }
        
        function closeModal() {
            const modal = document.getElementById("stockModal");
            modal.classList.remove("active");
        }
    </script>
</body>
</html>')
  
  writeLines(html_content, html_file)
  return(html_file)
}

# Generate and save HTML report
html_file <- generate_html_report(all_index_data)
cat("\n✅ HTML report saved to:", html_file, "\n")

# Save CSV results
csv_data <- data.frame()
for(index_name in sorted_indexes) {
  result <- index_results[[index_name]]
  stocks_df <- result$stocks %>%
    mutate(INDEX_NAME = index_name, INDEX_STRENGTH = result$index_strength) %>%
    select(INDEX_NAME, INDEX_STRENGTH, everything())
  csv_data <- rbind(csv_data, stocks_df)
}

csv_file <- file.path("reports", paste0("all_indexes_top5_analysis_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".csv"))
write_csv(csv_data, csv_file)
cat("✅ CSV results saved to:", csv_file, "\n")

