# =============================================================================
# GENERATE FINAL INTEGRATED REPORT
# =============================================================================
# This script generates comprehensive final reports integrating all analysis and backtesting results

library(dplyr)
library(lubridate)

# =============================================================================
# FUNCTIONS
# =============================================================================

# Function to load latest analysis and backtesting results
load_latest_results <- function() {
  cat("Loading latest analysis and backtesting results...\n")
  
  # Find latest analysis results
  analysis_files <- list.files("reports", pattern = "comprehensive_nse_enhanced_.*\\.csv", full.names = TRUE)
  if(length(analysis_files) == 0) {
    stop("No analysis results found")
  }
  latest_analysis_file <- analysis_files[order(file.info(analysis_files)$mtime, decreasing = TRUE)[1]]
  
  # Find latest backtesting results
  backtesting_files <- list.files("output/backtesting_results", pattern = "integrated_backtesting_results_.*\\.csv", full.names = TRUE)
  if(length(backtesting_files) == 0) {
    stop("No backtesting results found")
  }
  latest_backtesting_file <- backtesting_files[order(file.info(backtesting_files)$mtime, decreasing = TRUE)[1]]
  
  # Load data
  analysis_results <- read.csv(latest_analysis_file, stringsAsFactors = FALSE)
  backtesting_results <- read.csv(latest_backtesting_file, stringsAsFactors = FALSE)
  
  cat("✓ Loaded analysis results:", nrow(analysis_results), "stocks\n")
  cat("✓ Loaded backtesting results:", nrow(backtesting_results), "stocks\n")
  
  return(list(
    analysis = analysis_results,
    backtesting = backtesting_results,
    analysis_file = latest_analysis_file,
    backtesting_file = latest_backtesting_file
  ))
}

# Function to create comprehensive markdown report
create_comprehensive_markdown <- function(results) {
  cat("Creating comprehensive markdown report...\n")
  
  analysis_data <- results$analysis
  backtesting_data <- results$backtesting
  
  # Merge data
  integrated_data <- analysis_data %>%
    left_join(backtesting_data, by = "SYMBOL") %>%
    arrange(desc(CONFIDENCE_SCORE), desc(TECHNICAL_SCORE))
  
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Create comprehensive markdown content
  markdown_content <- paste0(
    "# 📊 COMPLETE INTEGRATED NSE ANALYSIS WITH BACKTESTING\n",
    "**Analysis Date:** ", Sys.Date(), " | **Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n",
    
    "## 🎯 Executive Summary\n\n",
    "This comprehensive report integrates NSE universe analysis with backtesting confidence scores and performance simulation, providing a complete view of market opportunities and risks.\n\n",
    
    "### 📈 Key Performance Metrics:\n",
    "- **Total Stocks Analyzed:** ", nrow(integrated_data), "\n",
    "- **High Confidence Stocks (≥70%):** ", sum(integrated_data$CONFIDENCE_SCORE >= 0.7, na.rm = TRUE), "\n",
    "- **Very High Confidence Stocks (≥80%):** ", sum(integrated_data$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE), "\n",
    "- **Average Confidence Score:** ", round(mean(integrated_data$CONFIDENCE_SCORE, na.rm = TRUE) * 100, 1), "%\n",
    "- **Average Simulated Return:** ", round(mean(integrated_data$SIMULATED_RETURN, na.rm = TRUE) * 100, 1), "%\n",
    "- **Average Win Rate:** ", round(mean(integrated_data$SIMULATED_WIN_RATE, na.rm = TRUE) * 100, 1), "%\n\n",
    
    "## 🏆 TOP 20 HIGH CONFIDENCE STOCKS\n\n",
    "| Rank | Stock | Company Name | Market Cap | Technical Score | Confidence Score | Trading Signal | Simulated Return | Win Rate | Performance |\n",
    "|------|-------|-------------|------------|-----------------|------------------|----------------|------------------|----------|-------------|\n"
  )
  
  # Add top 20 stocks
  top_20 <- integrated_data %>%
    filter(CONFIDENCE_SCORE >= 0.6) %>%
    arrange(desc(CONFIDENCE_SCORE)) %>%
    head(20)
  
  for(i in 1:nrow(top_20)) {
    stock <- top_20[i, ]
    markdown_content <- paste0(markdown_content,
      "| ", i, " | **", stock$SYMBOL, "** | ", stock$COMPANY_NAME, " | ", 
      stock$MARKET_CAP_CATEGORY, " | ", 
      round(stock$TECHNICAL_SCORE, 1), " | ", 
      round(stock$CONFIDENCE_SCORE * 100, 1), "% | ", 
      stock$TRADING_SIGNAL, " | ", 
      round(stock$SIMULATED_RETURN * 100, 1), "% | ", 
      round(stock$SIMULATED_WIN_RATE * 100, 1), "% | ", 
      stock$PERFORMANCE_CATEGORY, " |\n"
    )
  }
  
  # Add market breadth analysis
  markdown_content <- paste0(markdown_content,
    "\n## 📊 Market Breadth Analysis\n\n",
    "### Trading Signal Distribution:\n",
    "| Signal | Count | Percentage | Confidence Range |\n",
    "|--------|-------|------------|-----------------|\n"
  )
  
  signal_summary <- integrated_data %>%
    group_by(TRADING_SIGNAL) %>%
    summarise(
      COUNT = n(),
      AVG_CONFIDENCE = mean(CONFIDENCE_SCORE, na.rm = TRUE),
      AVG_RETURN = mean(SIMULATED_RETURN, na.rm = TRUE),
      .groups = 'drop'
    ) %>%
    mutate(PERCENTAGE = round(COUNT / nrow(integrated_data) * 100, 1))
  
  for(i in 1:nrow(signal_summary)) {
    signal <- signal_summary[i, ]
    markdown_content <- paste0(markdown_content,
      "| ", signal$TRADING_SIGNAL, " | ", signal$COUNT, " | ", 
      signal$PERCENTAGE, "% | ", 
      round(signal$AVG_CONFIDENCE * 100, 1), "% |\n"
    )
  }
  
  # Add confidence distribution
  markdown_content <- paste0(markdown_content,
    "\n### Confidence Score Distribution:\n",
    "| Category | Count | Avg Confidence | Avg Win Rate | Avg Return |\n",
    "|----------|-------|----------------|--------------|------------|\n"
  )
  
  confidence_dist <- integrated_data %>%
    group_by(CONFIDENCE_CATEGORY) %>%
    summarise(
      COUNT = n(),
      AVG_CONFIDENCE = mean(CONFIDENCE_SCORE, na.rm = TRUE),
      AVG_WIN_RATE = mean(SIMULATED_WIN_RATE, na.rm = TRUE),
      AVG_RETURN = mean(SIMULATED_RETURN, na.rm = TRUE),
      .groups = 'drop'
    ) %>%
    arrange(desc(AVG_CONFIDENCE))
  
  for(i in 1:nrow(confidence_dist)) {
    dist <- confidence_dist[i, ]
    markdown_content <- paste0(markdown_content,
      "| ", dist$CONFIDENCE_CATEGORY, " | ", dist$COUNT, " | ", 
      round(dist$AVG_CONFIDENCE * 100, 1), "% | ", 
      round(dist$AVG_WIN_RATE * 100, 1), "% | ", 
      round(dist$AVG_RETURN * 100, 1), "% |\n"
    )
  }
  
  # Add market cap analysis
  markdown_content <- paste0(markdown_content,
    "\n## 📈 Market Cap Category Analysis\n\n",
    "| Market Cap | Count | Avg Technical Score | Avg Confidence | Avg Return | Top Performer |\n",
    "|------------|-------|-------------------|----------------|------------|---------------|\n"
  )
  
  cap_summary <- integrated_data %>%
    group_by(MARKET_CAP_CATEGORY) %>%
    summarise(
      COUNT = n(),
      AVG_TECH_SCORE = mean(TECHNICAL_SCORE, na.rm = TRUE),
      AVG_CONFIDENCE = mean(CONFIDENCE_SCORE, na.rm = TRUE),
      AVG_RETURN = mean(SIMULATED_RETURN, na.rm = TRUE),
      TOP_STOCK = SYMBOL[which.max(TECHNICAL_SCORE)],
      TOP_SCORE = max(TECHNICAL_SCORE, na.rm = TRUE),
      .groups = 'drop'
    ) %>%
    arrange(desc(AVG_TECH_SCORE))
  
  for(i in 1:nrow(cap_summary)) {
    cap <- cap_summary[i, ]
    markdown_content <- paste0(markdown_content,
      "| ", cap$MARKET_CAP_CATEGORY, " | ", cap$COUNT, " | ", 
      round(cap$AVG_TECH_SCORE, 1), " | ", 
      round(cap$AVG_CONFIDENCE * 100, 1), "% | ", 
      round(cap$AVG_RETURN * 100, 1), "% | ", 
      cap$TOP_STOCK, " (", round(cap$TOP_SCORE, 1), ") |\n"
    )
  }
  
  # Add top performers by category
  markdown_content <- paste0(markdown_content,
    "\n## 🏅 Top Performers by Market Cap Category\n\n"
  )
  
  for(cap_category in unique(integrated_data$MARKET_CAP_CATEGORY)) {
    cap_stocks <- integrated_data %>%
      filter(MARKET_CAP_CATEGORY == cap_category) %>%
      arrange(desc(CONFIDENCE_SCORE)) %>%
      head(5)
    
    if(nrow(cap_stocks) > 0) {
      markdown_content <- paste0(markdown_content,
        "### ", cap_category, " - Top 5 by Confidence Score:\n",
        "| Rank | Stock | Technical Score | Confidence Score | Trading Signal | Simulated Return |\n",
        "|------|-------|-----------------|------------------|----------------|------------------|\n"
      )
      
      for(j in 1:nrow(cap_stocks)) {
        stock <- cap_stocks[j, ]
        markdown_content <- paste0(markdown_content,
          "| ", j, " | **", stock$SYMBOL, "** | ", 
          round(stock$TECHNICAL_SCORE, 1), " | ", 
          round(stock$CONFIDENCE_SCORE * 100, 1), "% | ", 
          stock$TRADING_SIGNAL, " | ", 
          round(stock$SIMULATED_RETURN * 100, 1), "% |\n"
        )
      }
      markdown_content <- paste0(markdown_content, "\n")
    }
  }
  
  # Add methodology
  markdown_content <- paste0(markdown_content,
    "\n## 🔧 Methodology\n\n",
    "### Technical Analysis Components:\n",
    "- **RSI Score (8 points):** Optimal range 40-70\n",
    "- **Price vs SMAs (10 points):** Above 10,20,50,100,200 SMAs\n",
    "- **SMA Crossovers (10 points):** 10>20, 20>50, 50>100, 100>200\n",
    "- **Relative Strength (20 points):** vs NIFTY500 over 50 days\n",
    "- **Volume Score (12 points):** vs 10-day average\n",
    "- **CAN SLIM Score (20 points):** William O'Neil methodology\n",
    "- **Minervini Score (20 points):** Mark Minervini methodology\n",
    "- **Fundamental Score (25 points):** Enhanced fundamental analysis\n\n",
    
    "### Confidence Score Calculation:\n",
    "- **RSI Confidence (30%):** Based on RSI optimal ranges (40-70)\n",
    "- **Technical Score Confidence (40%):** Normalized technical score\n",
    "- **Relative Strength Confidence (30%):** Performance vs NIFTY500\n\n",
    
    "### Performance Simulation:\n",
    "- **Win Rate:** Simulated based on confidence score and signal type\n",
    "- **Return:** Simulated based on confidence score and signal type\n",
    "- **Risk-Adjusted Return:** Return adjusted for win rate\n\n",
    
    "## 📋 Investment Recommendations\n\n",
    "### 🥇 High Priority Picks (Confidence ≥80%):\n"
  )
  
  high_confidence <- integrated_data %>%
    filter(CONFIDENCE_SCORE >= 0.8) %>%
    arrange(desc(CONFIDENCE_SCORE)) %>%
    head(10)
  
  for(k in 1:nrow(high_confidence)) {
    stock <- high_confidence[k, ]
    markdown_content <- paste0(markdown_content,
      k, ". **", stock$SYMBOL, "** - Confidence: ", round(stock$CONFIDENCE_SCORE * 100, 1), 
      "%, Return: ", round(stock$SIMULATED_RETURN * 100, 1), 
      "%, Win Rate: ", round(stock$SIMULATED_WIN_RATE * 100, 1), "%\n"
    )
  }
  
  markdown_content <- paste0(markdown_content,
    "\n### 🥈 Moderate Priority Picks (Confidence 70-80%):\n"
  )
  
  moderate_confidence <- integrated_data %>%
    filter(CONFIDENCE_SCORE >= 0.7 & CONFIDENCE_SCORE < 0.8) %>%
    arrange(desc(CONFIDENCE_SCORE)) %>%
    head(10)
  
  for(k in 1:nrow(moderate_confidence)) {
    stock <- moderate_confidence[k, ]
    markdown_content <- paste0(markdown_content,
      k, ". **", stock$SYMBOL, "** - Confidence: ", round(stock$CONFIDENCE_SCORE * 100, 1), 
      "%, Return: ", round(stock$SIMULATED_RETURN * 100, 1), 
      "%, Win Rate: ", round(stock$SIMULATED_WIN_RATE * 100, 1), "%\n"
    )
  }
  
  # Add footer
  markdown_content <- paste0(markdown_content,
    "\n---\n",
    "**Report Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n",
    "**Data Source:** NSE Historical Data + Backtesting Simulation\n",
    "**Analysis Method:** Enhanced Technical Scoring with CAN SLIM & Minervini Indicators\n"
  )
  
  # Save markdown file
  output_dir <- "output/final_reports"
  if(!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  markdown_file <- file.path(output_dir, paste0("complete_integrated_analysis_report_", timestamp, ".md"))
  writeLines(markdown_content, markdown_file)
  
  cat("✓ Comprehensive markdown report saved to:", markdown_file, "\n")
  
  return(list(
    integrated_data = integrated_data,
    markdown_file = markdown_file
  ))
}

# Function to create comprehensive HTML dashboard
create_comprehensive_html <- function(results, integrated_data) {
  cat("Creating comprehensive HTML dashboard...\n")
  
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Get top 50 stocks for the dashboard
  top_50_stocks <- integrated_data %>%
    filter(CONFIDENCE_SCORE >= 0.6) %>%
    arrange(desc(CONFIDENCE_SCORE)) %>%
    head(50)
  
  # Create JavaScript data array
  js_data <- ""
  for(i in 1:nrow(top_50_stocks)) {
    stock <- top_50_stocks[i, ]
    js_data <- paste0(js_data, 
      "            {\n",
      "                rank: ", i, ",\n",
      "                symbol: '", stock$SYMBOL, "',\n",
      "                companyName: '", stock$COMPANY_NAME, "',\n",
      "                marketCap: '", stock$MARKET_CAP_CATEGORY, "',\n",
      "                currentPrice: ", stock$CURRENT_PRICE, ",\n",
      "                change1D: ", ifelse(is.na(stock$CHANGE_1D), 0, stock$CHANGE_1D), ",\n",
      "                change1W: ", ifelse(is.na(stock$CHANGE_1W), 0, stock$CHANGE_1W), ",\n",
      "                change1M: ", ifelse(is.na(stock$CHANGE_1M), 0, stock$CHANGE_1M), ",\n",
      "                technicalScore: ", stock$TECHNICAL_SCORE, ",\n",
      "                rsi: ", stock$RSI, ",\n",
      "                relativeStrength: ", ifelse(is.na(stock$RELATIVE_STRENGTH), 0, stock$RELATIVE_STRENGTH), ",\n",
      "                canSlim: ", stock$CAN_SLIM_SCORE, ",\n",
      "                minervini: ", stock$MINERVINI_SCORE, ",\n",
      "                fundamental: ", ifelse(is.na(stock$ENHANCED_FUND_SCORE), 0, stock$ENHANCED_FUND_SCORE), ",\n",
      "                trendSignal: '", stock$TREND_SIGNAL, "',\n",
      "                tradingSignal: '", stock$TRADING_SIGNAL, "',\n",
      "                confidenceScore: ", round(stock$CONFIDENCE_SCORE * 100, 1), ",\n",
      "                simulatedReturn: ", round(stock$SIMULATED_RETURN * 100, 1), ",\n",
      "                simulatedWinRate: ", round(stock$SIMULATED_WIN_RATE * 100, 1), ",\n",
      "                performanceCategory: '", stock$PERFORMANCE_CATEGORY, "'\n",
      "            }")
    
    if(i < nrow(top_50_stocks)) {
      js_data <- paste0(js_data, ",\n")
    }
  }
  
  # Create comprehensive HTML content
  html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Complete Integrated NSE Analysis Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
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

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px 24px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            text-align: center;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .stat-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0,0,0,0.2);
        }

        .stat-number {
            font-size: 3rem;
            font-weight: 300;
            color: #1976d2;
            margin-bottom: 12px;
            line-height: 1;
        }

        .stat-label {
            color: #616161;
            font-size: 0.875rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }

        .chart-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .chart-title {
            font-size: 1.5rem;
            font-weight: 500;
            margin-bottom: 24px;
            color: #1976d2;
            text-align: center;
            letter-spacing: 0.2px;
        }

        .stocks-table-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .table-title {
            font-size: 1.5rem;
            font-weight: 500;
            color: #1976d2;
            letter-spacing: 0.2px;
        }

        .filters {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 10px 20px;
            border: 2px solid #1976d2;
            background: rgba(255, 255, 255, 0.9);
            color: #1976d2;
            border-radius: 24px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 0.875rem;
            font-weight: 500;
            letter-spacing: 0.5px;
        }

        .filter-btn.active,
        .filter-btn:hover {
            background: #1976d2;
            color: white;
            box-shadow: 0 4px 12px rgba(25, 118, 210, 0.3);
            transform: translateY(-2px);
        }

        .search-box {
            padding: 12px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 24px;
            font-size: 0.875rem;
            outline: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            background: rgba(255, 255, 255, 0.9);
        }

        .search-box:focus {
            border-color: #1976d2;
            box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.1);
            background: white;
        }

        .stocks-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }

        .stocks-table th {
            background: #f5f5f5;
            padding: 16px 12px;
            text-align: left;
            font-weight: 600;
            color: #1976d2;
            border-bottom: 2px solid #e0e0e0;
            font-size: 0.875rem;
            letter-spacing: 0.5px;
        }

        .stocks-table td {
            padding: 12px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 0.875rem;
        }

        .stocks-table tr:hover {
            background: rgba(25, 118, 210, 0.04);
            transition: background 0.2s ease;
        }

        .signal-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .signal-strong-buy { background: linear-gradient(135deg, #4CAF50, #66BB6A); color: white; }
        .signal-buy { background: linear-gradient(135deg, #8BC34A, #9CCC65); color: white; }
        .signal-hold { background: linear-gradient(135deg, #FFC107, #FFD54F); color: #333; }
        .signal-weak-hold { background: linear-gradient(135deg, #FF9800, #FFB74D); color: white; }
        .signal-sell { background: linear-gradient(135deg, #F44336, #EF5350); color: white; }

        .trend-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .trend-strong-bullish { background: linear-gradient(135deg, #4CAF50, #66BB6A); color: white; }
        .trend-bullish { background: linear-gradient(135deg, #8BC34A, #9CCC65); color: white; }
        .trend-neutral { background: linear-gradient(135deg, #FFC107, #FFD54F); color: #333; }
        .trend-bearish { background: linear-gradient(135deg, #FF9800, #FFB74D); color: white; }
        .trend-strong-bearish { background: linear-gradient(135deg, #F44336, #EF5350); color: white; }

        .market-cap-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .market-cap-large_cap { background: linear-gradient(135deg, #2196F3, #42A5F5); color: white; }
        .market-cap-mid_cap { background: linear-gradient(135deg, #9C27B0, #BA68C8); color: white; }
        .market-cap-small_cap { background: linear-gradient(135deg, #FF5722, #FF7043); color: white; }
        .market-cap-micro_cap { background: linear-gradient(135deg, #607D8B, #90A4AE); color: white; }

        .positive { color: #2E7D32; font-weight: 600; }
        .negative { color: #D32F2F; font-weight: 600; }

        .confidence-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .confidence-high { background: linear-gradient(135deg, #4CAF50, #66BB6A); color: white; }
        .confidence-medium { background: linear-gradient(135deg, #FFC107, #FFD54F); color: #333; }
        .confidence-low { background: linear-gradient(135deg, #F44336, #EF5350); color: white; }

        @media (max-width: 768px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Complete Integrated NSE Analysis Dashboard</h1>
            <p>Comprehensive Technical Analysis with Backtesting Confidence Scores</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">', nrow(integrated_data), '</div>
                <div class="stat-label">Total Stocks Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(integrated_data$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE), '</div>
                <div class="stat-label">Very High Confidence (≥80%)</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(integrated_data$CONFIDENCE_SCORE >= 0.7, na.rm = TRUE), '</div>
                <div class="stat-label">High Confidence (≥70%)</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', round(mean(integrated_data$CONFIDENCE_SCORE, na.rm = TRUE) * 100, 1), '%</div>
                <div class="stat-label">Average Confidence Score</div>
            </div>
        </div>

        <div class="stocks-table-container">
            <div class="table-header">
                <div class="table-title">📋 Top 50 High Confidence Stocks</div>
                <div class="filters">
                    <input type="text" id="stockSearch" class="search-box" placeholder="Search stocks...">
                    <button class="filter-btn active" data-filter="all">All</button>
                    <button class="filter-btn" data-filter="very-high">Very High Confidence</button>
                    <button class="filter-btn" data-filter="high">High Confidence</button>
                    <button class="filter-btn" data-filter="large-cap">Large Cap</button>
                    <button class="filter-btn" data-filter="mid-cap">Mid Cap</button>
                    <button class="filter-btn" data-filter="small-cap">Small Cap</button>
                    <button class="filter-btn" data-filter="micro-cap">Micro Cap</button>
                </div>
            </div>
            <table class="stocks-table" id="stocksTable">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Stock</th>
                        <th>Company Name</th>
                        <th>Market Cap</th>
                        <th>Price</th>
                        <th>1D</th>
                        <th>1W</th>
                        <th>1M</th>
                        <th>Tech Score</th>
                        <th>Confidence</th>
                        <th>Signal</th>
                        <th>Sim Return</th>
                        <th>Win Rate</th>
                        <th>Performance</th>
                    </tr>
                </thead>
                <tbody id="stocksTableBody">
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Stock data from analysis
        const stocksData = [
', js_data, '
        ];

        // Populate stocks table
        function populateStocksTable(data = stocksData) {
            const tbody = document.getElementById("stocksTableBody");
            tbody.innerHTML = "";

            data.forEach((stock, index) => {
                const row = document.createElement("tr");
                
                // Determine confidence class
                let confidenceClass = "confidence-low";
                if (stock.confidenceScore >= 80) confidenceClass = "confidence-high";
                else if (stock.confidenceScore >= 70) confidenceClass = "confidence-medium";
                
                row.innerHTML = `
                    <td>${index + 1}</td>
                    <td><strong>${stock.symbol}</strong></td>
                    <td>${stock.companyName}</td>
                    <td><span class="market-cap-badge market-cap-${stock.marketCap.toLowerCase()}">${stock.marketCap.replace("_", " ")}</span></td>
                    <td>₹${stock.currentPrice.toLocaleString()}</td>
                    <td class="${stock.change1D >= 0 ? "positive" : "negative"}">${stock.change1D >= 0 ? "+" : ""}${stock.change1D.toFixed(2)}%</td>
                    <td class="${stock.change1W >= 0 ? "positive" : "negative"}">${stock.change1W >= 0 ? "+" : ""}${stock.change1W.toFixed(2)}%</td>
                    <td class="${stock.change1M >= 0 ? "positive" : "negative"}">${stock.change1M >= 0 ? "+" : ""}${stock.change1M.toFixed(2)}%</td>
                    <td><strong>${stock.technicalScore.toFixed(1)}</strong></td>
                    <td><span class="confidence-badge ${confidenceClass}">${stock.confidenceScore}%</span></td>
                    <td><span class="signal-badge signal-${stock.tradingSignal.toLowerCase().replace("_", "-")}">${stock.tradingSignal.replace("_", " ")}</span></td>
                    <td class="${stock.simulatedReturn >= 0 ? "positive" : "negative"}">${stock.simulatedReturn >= 0 ? "+" : ""}${stock.simulatedReturn.toFixed(1)}%</td>
                    <td>${stock.simulatedWinRate.toFixed(1)}%</td>
                    <td><strong>${stock.performanceCategory}</strong></td>
                `;
                
                tbody.appendChild(row);
            });
        }

        // Filter functionality
        function setupFilters() {
            const filterBtns = document.querySelectorAll(".filter-btn");
            const searchBox = document.getElementById("stockSearch");

            filterBtns.forEach(btn => {
                btn.addEventListener("click", () => {
                    filterBtns.forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    applyFilters();
                });
            });

            searchBox.addEventListener("input", applyFilters);
        }

        function applyFilters() {
            const activeFilter = document.querySelector(".filter-btn.active").dataset.filter;
            const searchTerm = document.getElementById("stockSearch").value.toLowerCase();

            let filteredData = stocksData.filter(stock => {
                const matchesSearch = stock.symbol.toLowerCase().includes(searchTerm) || 
                                    stock.companyName.toLowerCase().includes(searchTerm);
                let matchesFilter = true;

                switch (activeFilter) {
                    case "very-high":
                        matchesFilter = stock.confidenceScore >= 80;
                        break;
                    case "high":
                        matchesFilter = stock.confidenceScore >= 70;
                        break;
                    case "large-cap":
                        matchesFilter = stock.marketCap === "LARGE_CAP";
                        break;
                    case "mid-cap":
                        matchesFilter = stock.marketCap === "MID_CAP";
                        break;
                    case "small-cap":
                        matchesFilter = stock.marketCap === "SMALL_CAP";
                        break;
                    case "micro-cap":
                        matchesFilter = stock.marketCap === "MICRO_CAP";
                        break;
                }

                return matchesSearch && matchesFilter;
            });

            populateStocksTable(filteredData);
        }

        // Initialize everything when page loads
        document.addEventListener("DOMContentLoaded", () => {
            populateStocksTable(stocksData);
            setupFilters();
        });
    </script>
</body>
</html>')
  
  # Save HTML file
  output_dir <- "output/final_reports"
  if(!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  html_file <- file.path(output_dir, paste0("complete_integrated_analysis_dashboard_", timestamp, ".html"))
  writeLines(html_content, html_file)
  
  cat("✓ Comprehensive HTML dashboard saved to:", html_file, "\n")
  
  return(html_file)
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

cat("Generating final integrated reports...\n")
cat("============================================================\n")

# Load latest results
results <- load_latest_results()

# Create comprehensive markdown report
markdown_output <- create_comprehensive_markdown(results)

# Create comprehensive HTML dashboard
html_file <- create_comprehensive_html(results, markdown_output$integrated_data)

# Print final summary
cat("\n" , "=", 60, "\n")
cat("FINAL INTEGRATED REPORTS GENERATED SUCCESSFULLY\n")
cat("=", 60, "\n")

cat("\n📊 ANALYSIS SUMMARY:\n")
cat("Total Stocks Analyzed:", nrow(markdown_output$integrated_data), "\n")
cat("High Confidence Stocks (≥70%):", sum(markdown_output$integrated_data$CONFIDENCE_SCORE >= 0.7, na.rm = TRUE), "\n")
cat("Very High Confidence Stocks (≥80%):", sum(markdown_output$integrated_data$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE), "\n")
cat("Average Confidence Score:", round(mean(markdown_output$integrated_data$CONFIDENCE_SCORE, na.rm = TRUE) * 100, 1), "%\n")
cat("Average Simulated Return:", round(mean(markdown_output$integrated_data$SIMULATED_RETURN, na.rm = TRUE) * 100, 1), "%\n")
cat("Average Win Rate:", round(mean(markdown_output$integrated_data$SIMULATED_WIN_RATE, na.rm = TRUE) * 100, 1), "%\n")

cat("\n🎯 TOP 5 HIGH CONFIDENCE STOCKS:\n")
top_5 <- markdown_output$integrated_data %>%
  filter(CONFIDENCE_SCORE >= 0.8) %>%
  arrange(desc(CONFIDENCE_SCORE)) %>%
  head(5) %>%
  select(SYMBOL, TRADING_SIGNAL, TECHNICAL_SCORE, CONFIDENCE_SCORE, 
         SIMULATED_RETURN, SIMULATED_WIN_RATE, PERFORMANCE_CATEGORY)
print(top_5)

cat("\n💾 FILES GENERATED:\n")
cat("Comprehensive Markdown Report:", markdown_output$markdown_file, "\n")
cat("Interactive HTML Dashboard:", html_file, "\n")

cat("\n" , "=", 60, "\n")
cat("✅ Final integrated reports completed successfully!\n")
cat("Check the output/final_reports/ directory for all reports.\n")
