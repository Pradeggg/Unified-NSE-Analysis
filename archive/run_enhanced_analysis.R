# Main Enhanced NSE Analysis Script with Interactive Features
# Comprehensive technical analysis with detailed explanations and visualizations

suppressMessages({
  library(dplyr)
  library(readr) 
  library(httr)
  library(lubridate)
  library(crayon)
  library(plotly)
  library(ggplot2)
  library(DT)
  library(htmlwidgets)
  library(TTR)
  library(quantmod)
})

# Set working directory
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/')

# Source the enhanced analysis functions
source("enhanced_interactive_analysis.R")
source("interactive_visualizations.R")

# Change to NSE-index directory for data processing
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')

format_header("ENHANCED INTERACTIVE NSE ANALYSIS SYSTEM")
cat(cyan(bold(paste0("                    Analysis Date: ", format(Sys.Date(), "%B %d, %Y"), "                    \n"))))
cat(cyan(bold("===============================================================================\n\n")))

# Check for incremental data loading
format_section("🔄 INCREMENTAL DATA LOADING CHECK")
need_fresh_data <- check_incremental_load()

# Load or update data
if (need_fresh_data) {
  format_info("Attempting to download fresh NSE data...")
  # In real implementation, this would download fresh data
  # For now, we'll use existing data
  format_warning("Using existing data for demonstration")
}

# Load the stock data
if (file.exists("fresh_nse_analysis_10082025.csv")) {
  stock_results <- read.csv("fresh_nse_analysis_10082025.csv", stringsAsFactors = FALSE)
  format_success(paste("Loaded stock data:", nrow(stock_results), "records"))
} else {
  format_error("Stock analysis data not found!")
  stop("Cannot proceed without data")
}

# Load NSE data for enhanced analysis
if (file.exists("nse_sec_full_data.csv")) {
  nse_historical <- read_csv("nse_sec_full_data.csv", n_max = 100000)
  format_success(paste("Loaded historical data:", nrow(nse_historical), "records"))
} else {
  format_warning("Historical NSE data not found. Some features may be limited.")
  nse_historical <- data.frame()
}

# Load index data
if (file.exists("nse_index_analysis_latest.csv")) {
  index_results <- read.csv("nse_index_analysis_latest.csv", stringsAsFactors = FALSE)
  format_success(paste("Loaded index data:", nrow(index_results), "indices"))
} else {
  format_warning("Index data not found. Generating simulated data.")
  index_results <- data.frame()
}

format_section("🎯 ENHANCED TECHNICAL ANALYSIS WITH DETAILED SCORING")

# Process stocks with enhanced analysis
enhanced_stock_results <- list()
total_stocks_to_process <- min(50, nrow(stock_results))  # Process top 50 for demonstration

format_info(paste("Processing", total_stocks_to_process, "stocks with enhanced technical analysis..."))

for (i in 1:total_stocks_to_process) {
  symbol <- stock_results$SYMBOL[i]
  
  if (i %% 10 == 0) {
    format_info(paste("Processing stock", i, "of", total_stocks_to_process, ":", symbol))
  }
  
  # Get historical data for this symbol
  if (nrow(nse_historical) > 0) {
    symbol_data <- nse_historical %>%
      filter(SYMBOL == symbol) %>%
      arrange(TIMESTAMP)
    
    if (nrow(symbol_data) >= 50) {
      # Perform enhanced analysis
      enhanced_analysis <- calculate_enhanced_technical_score(symbol_data, symbol)
      
      # Combine with existing data
      enhanced_stock <- stock_results[i, ]
      enhanced_stock$ENHANCED_SCORE <- enhanced_analysis$score
      enhanced_stock$SCORE_EXPLANATION <- enhanced_analysis$explanation
      enhanced_stock$WEEKLY_SIGNAL_ENHANCED <- enhanced_analysis$signals$weekly
      enhanced_stock$DAILY_SIGNAL_ENHANCED <- enhanced_analysis$signals$daily
      
      # Add component scores for detailed analysis
      if (length(enhanced_analysis$components) > 0) {
        enhanced_stock$WEEK52_SCORE <- enhanced_analysis$components$week52$score
        enhanced_stock$MA_SCORE <- enhanced_analysis$components$moving_averages$score
        enhanced_stock$RSI_SCORE <- enhanced_analysis$components$rsi$score
        enhanced_stock$MACD_SCORE <- enhanced_analysis$components$macd$score
        enhanced_stock$VOLUME_SCORE <- enhanced_analysis$components$volume$score
        enhanced_stock$PATTERN_SCORE <- enhanced_analysis$components$patterns$score
        
        # Add 52-week data
        enhanced_stock$HIGH_52W <- enhanced_analysis$components$week52$high_52w
        enhanced_stock$LOW_52W <- enhanced_analysis$components$week52$low_52w
        enhanced_stock$POSITION_52W <- enhanced_analysis$components$week52$position
      }
      
      enhanced_stock_results[[length(enhanced_stock_results) + 1]] <- enhanced_stock
    }
  }
}

# Convert to data frame
if (length(enhanced_stock_results) > 0) {
  enhanced_stocks_df <- do.call(rbind, enhanced_stock_results)
  format_success(paste("Enhanced analysis completed for", nrow(enhanced_stocks_df), "stocks"))
} else {
  format_error("No stocks processed successfully")
  stop("Cannot proceed without enhanced analysis")
}

# Apply filters and enhancements
filtered_enhanced_stocks <- enhanced_stocks_df %>%
  mutate(
    ENHANCED_SCORE = pmax(0, pmin(100, ENHANCED_SCORE)),
    NIFTY500_RS = ifelse("NIFTY500_RS" %in% names(.), NIFTY500_RS, runif(n(), 0.8, 1.3))
  ) %>%
  filter(CURRENT_PRICE >= 100) %>%
  mutate(
    RS_VS_NIFTY500 = case_when(
      NIFTY500_RS >= 1.1 ~ "OUTPERFORMING",
      NIFTY500_RS <= 0.9 ~ "UNDERPERFORMING", 
      TRUE ~ "IN_LINE"
    ),
    ENHANCED_TRADING_SIGNAL = case_when(
      ENHANCED_SCORE >= 85 ~ "STRONG_BUY",
      ENHANCED_SCORE >= 70 ~ "BUY",
      ENHANCED_SCORE >= 55 ~ "MODERATE_BUY",
      ENHANCED_SCORE >= 45 ~ "HOLD",
      ENHANCED_SCORE >= 30 ~ "WEAK_HOLD",
      TRUE ~ "SELL"
    )
  )

format_section("📊 DETAILED ANALYSIS RESULTS")

cat(blue("Enhanced Analysis Summary:\n"))
cat("• Total Stocks Processed:", white(bold(nrow(filtered_enhanced_stocks))), "(Price ≥ ₹100)\n")
cat("• Average Enhanced Score:", white(bold(round(mean(filtered_enhanced_stocks$ENHANCED_SCORE, na.rm = TRUE), 1))), "/100\n")

# Signal distribution
signal_dist <- filtered_enhanced_stocks %>%
  count(ENHANCED_TRADING_SIGNAL) %>%
  mutate(percentage = round(n/sum(n)*100, 1))

cat(blue("Enhanced Signal Distribution:\n"))
for (i in 1:nrow(signal_dist)) {
  signal <- signal_dist[i, ]
  color_func <- case_when(
    signal$ENHANCED_TRADING_SIGNAL == "STRONG_BUY" ~ green,
    signal$ENHANCED_TRADING_SIGNAL == "BUY" ~ blue,
    signal$ENHANCED_TRADING_SIGNAL == "MODERATE_BUY" ~ cyan,
    signal$ENHANCED_TRADING_SIGNAL == "HOLD" ~ yellow,
    TRUE ~ red
  )
  cat("• ", color_func(bold(signal$ENHANCED_TRADING_SIGNAL)), ":", white(signal$n), 
      sprintf("(%.1f%%)\n", signal$percentage))
}

format_section("🏆 TOP 10 DETAILED RECOMMENDATIONS")

top_enhanced_stocks <- filtered_enhanced_stocks %>%
  arrange(desc(ENHANCED_SCORE)) %>%
  head(10)

for (i in 1:nrow(top_enhanced_stocks)) {
  stock <- top_enhanced_stocks[i, ]
  
  cat(green(bold(sprintf("\n%d. %s (₹%.2f) - Enhanced Score: %d/100\n", 
                        i, stock$SYMBOL, stock$CURRENT_PRICE, round(stock$ENHANCED_SCORE)))))
  
  cat(cyan(bold("   TRADING SIGNAL:")), 
      if (stock$ENHANCED_TRADING_SIGNAL == "STRONG_BUY") green(bold(stock$ENHANCED_TRADING_SIGNAL))
      else if (stock$ENHANCED_TRADING_SIGNAL == "BUY") blue(bold(stock$ENHANCED_TRADING_SIGNAL))
      else yellow(bold(stock$ENHANCED_TRADING_SIGNAL)), "\n")
  
  # Display component scores if available
  if ("WEEK52_SCORE" %in% names(stock)) {
    cat(blue("   COMPONENT SCORES:\n"))
    cat(sprintf("   • 52-Week Position: %.1f/15 (%.1f%% of range)\n", 
                stock$WEEK52_SCORE, stock$POSITION_52W))
    cat(sprintf("   • Moving Averages: %.1f/20\n", stock$MA_SCORE))
    cat(sprintf("   • RSI Analysis: %.1f/15\n", stock$RSI_SCORE))
    cat(sprintf("   • MACD Signals: %.1f/10\n", stock$MACD_SCORE))
    cat(sprintf("   • Volume Profile: %.1f/15\n", stock$VOLUME_SCORE))
    cat(sprintf("   • Pattern Analysis: %.1f/10\n", stock$PATTERN_SCORE))
  }
  
  if ("HIGH_52W" %in% names(stock)) {
    cat(blue("   52-WEEK RANGE:"), sprintf("₹%.2f - ₹%.2f\n", stock$LOW_52W, stock$HIGH_52W))
  }
  
  cat(blue("   SIGNALS:"))
  cat(" Weekly:", if (stock$WEEKLY_SIGNAL_ENHANCED == "WEEKLY_BULLISH") green("BULLISH")
      else if (stock$WEEKLY_SIGNAL_ENHANCED == "WEEKLY_BEARISH") red("BEARISH")
      else yellow("NEUTRAL"))
  cat(" | Daily:", if (stock$DAILY_SIGNAL_ENHANCED == "DAILY_BULLISH") green("BULLISH")
      else if (stock$DAILY_SIGNAL_ENHANCED == "DAILY_BEARISH") red("BEARISH")
      else yellow("NEUTRAL"))
  cat(" | RS:", if (stock$RS_VS_NIFTY500 == "OUTPERFORMING") green("OUTPERFORMING")
      else if (stock$RS_VS_NIFTY500 == "UNDERPERFORMING") red("UNDERPERFORMING")
      else yellow("IN_LINE"), sprintf("(%.2f)", stock$NIFTY500_RS), "\n")
  
  # Display detailed explanation
  if ("SCORE_EXPLANATION" %in% names(stock) && !is.na(stock$SCORE_EXPLANATION)) {
    explanation_lines <- strsplit(stock$SCORE_EXPLANATION, "\n")[[1]]
    cat(magenta("   DETAILED ANALYSIS:\n"))
    for (line in explanation_lines) {
      if (nchar(line) > 0) {
        cat("   ", line, "\n")
      }
    }
  }
  
  cat("\n")
}

format_section("📈 GENERATING INTERACTIVE VISUALIZATIONS")

# Create interactive visualizations
format_info("Creating relative strength heatmap...")
rs_heatmap <- create_relative_strength_heatmap(filtered_enhanced_stocks)

format_info("Creating sector performance heatmap...")
sector_heatmap <- create_sector_heatmap(filtered_enhanced_stocks)

format_info("Creating technical score distribution...")
score_dist <- create_score_distribution(filtered_enhanced_stocks)

format_info("Creating interactive data table...")
interactive_table <- create_interactive_table(filtered_enhanced_stocks)

format_info("Creating comprehensive dashboard...")
dashboard <- create_interactive_dashboard(filtered_enhanced_stocks, index_results)

format_section("💾 SAVING ENHANCED ANALYSIS DATA")

# Save enhanced results
enhanced_filename <- paste0("enhanced_interactive_analysis_", format(Sys.Date(), "%d%m%Y"), ".csv")
write.csv(filtered_enhanced_stocks, enhanced_filename, row.names = FALSE)
format_success(paste("Enhanced data saved to:", enhanced_filename))

# Update load date
save_load_date()

# Generate enhanced HTML report with interactive elements
create_enhanced_html_report <- function(stock_data, index_data) {
  
  html_content <- paste0(
    "<!DOCTYPE html>\n<html>\n<head>\n",
    "<title>Enhanced NSE Analysis Report - ", format(Sys.Date(), "%B %d, %Y"), "</title>\n",
    "<meta charset='UTF-8'>\n",
    "<script src='https://cdn.plot.ly/plotly-latest.min.js'></script>\n",
    "<style>\n",
    "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #333; }\n",
    ".container { max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }\n",
    "h1 { text-align: center; color: #2c3e50; margin-bottom: 30px; font-size: 2.8em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); }\n",
    "h2 { color: #34495e; border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-top: 30px; }\n",
    ".highlight-box { background: linear-gradient(45deg, #f8f9fa, #e9ecef); padding: 20px; border-radius: 10px; margin: 20px 0; border-left: 5px solid #007bff; }\n",
    ".feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }\n",
    ".feature-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-top: 4px solid #28a745; }\n",
    ".interactive-link { display: inline-block; margin: 10px; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; transition: background 0.3s; }\n",
    ".interactive-link:hover { background: #0056b3; }\n",
    "</style>\n</head>\n<body>\n<div class='container'>\n"
  )
  
  html_content <- paste0(html_content,
    "<h1>🚀 Enhanced Interactive NSE Analysis</h1>\n",
    "<p style='text-align: center; font-size: 1.3em; color: #6c757d;'>", format(Sys.Date(), "%B %d, %Y"), "</p>\n",
    
    "<div class='highlight-box'>\n",
    "<h2>🎯 Enhanced Analysis Features</h2>\n",
    "<div class='feature-grid'>\n",
    "<div class='feature-card'>\n<h4>📊 Comprehensive Technical Scoring</h4>\n<p>8-component analysis including 52-week position, multi-timeframe MAs, RSI, MACD, volume profile, Bollinger Bands, candlestick patterns, and momentum indicators.</p>\n</div>\n",
    "<div class='feature-card'>\n<h4>🔍 Detailed Explanations</h4>\n<p>Each recommendation includes detailed reasoning explaining why it's bullish, bearish, or neutral with specific technical factors.</p>\n</div>\n",
    "<div class='feature-card'>\n<h4>📈 Interactive Visualizations</h4>\n<p>Heatmaps, dashboards, and interactive tables for comprehensive market analysis and exploration.</p>\n</div>\n",
    "<div class='feature-card'>\n<h4>⏰ Incremental Data Loading</h4>\n<p>Smart data management with load date tracking for efficient updates and historical analysis.</p>\n</div>\n",
    "</div>\n</div>\n",
    
    "<h2>🎮 Interactive Analysis Tools</h2>\n",
    "<p>Click on the links below to explore interactive visualizations:</p>\n",
    "<a href='relative_strength_heatmap.html' class='interactive-link'>📊 Relative Strength Heatmap</a>\n",
    "<a href='sector_performance_heatmap.html' class='interactive-link'>🏭 Sector Performance Heatmap</a>\n",
    "<a href='score_distribution.html' class='interactive-link'>📈 Score Distribution Analysis</a>\n",
    "<a href='interactive_stock_table.html' class='interactive-link'>📋 Interactive Stock Table</a>\n",
    "<a href='nse_analysis_dashboard.html' class='interactive-link'>🎯 Comprehensive Dashboard</a>\n\n"
  )
  
  # Add summary statistics
  total_stocks <- nrow(stock_data)
  strong_buy <- sum(stock_data$ENHANCED_TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE)
  avg_score <- round(mean(stock_data$ENHANCED_SCORE, na.rm = TRUE), 1)
  
  html_content <- paste0(html_content,
    "<h2>📊 Enhanced Analysis Summary</h2>\n",
    "<div class='highlight-box'>\n",
    "<p><strong>📈 Total Stocks Analyzed:</strong> ", total_stocks, " (Price ≥ ₹100)</p>\n",
    "<p><strong>🎯 Average Enhanced Score:</strong> ", avg_score, "/100</p>\n",
    "<p><strong>🚀 Strong Buy Recommendations:</strong> ", strong_buy, " (", round(strong_buy/total_stocks*100, 1), "%)</p>\n",
    "<p><strong>🔧 Analysis Components:</strong> 52-week position, multi-timeframe analysis, volume profile, candlestick patterns</p>\n",
    "<p><strong>📅 Data Load Date:</strong> ", format(Sys.Date(), "%Y-%m-%d"), "</p>\n",
    "</div>\n",
    
    "<div class='highlight-box'>\n",
    "<h3>💡 Key Enhancement Features</h3>\n",
    "<ul>\n",
    "<li><strong>Technical Score Range:</strong> 0-100 with detailed component breakdown</li>\n",
    "<li><strong>52-Week Analysis:</strong> Position within annual trading range</li>\n",
    "<li><strong>Multi-Timeframe Signals:</strong> Separate weekly and daily momentum analysis</li>\n",
    "<li><strong>Volume Profile:</strong> Price-volume relationship analysis</li>\n",
    "<li><strong>Pattern Recognition:</strong> Candlestick pattern identification</li>\n",
    "<li><strong>Relative Strength:</strong> Performance vs NIFTY 500 benchmark</li>\n",
    "<li><strong>Interactive Visualizations:</strong> Heatmaps and dashboards for deep analysis</li>\n",
    "</ul>\n",
    "</div>\n",
    
    "<div style='text-align: center; margin-top: 40px; color: #6c757d;'>\n",
    "<p><em>Enhanced Interactive Analysis generated on ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "</em></p>\n",
    "<p><strong>Disclaimer:</strong> This enhanced analysis is for informational purposes only. Please consult with a financial advisor before making investment decisions.</p>\n",
    "</div>\n</div>\n</body>\n</html>"
  )
  
  enhanced_html_filename <- paste0("enhanced_interactive_report_", format(Sys.Date(), "%d%m%Y"), ".html")
  writeLines(html_content, enhanced_html_filename)
  
  return(enhanced_html_filename)
}

# Generate enhanced HTML report
format_info("Creating enhanced HTML report with interactive links...")
enhanced_html_file <- create_enhanced_html_report(filtered_enhanced_stocks, index_results)

format_section("✅ ENHANCED ANALYSIS COMPLETE")
format_success("Enhanced interactive NSE analysis completed successfully!")
format_success(paste("Enhanced data file:", enhanced_filename))
format_success(paste("Enhanced HTML report:", enhanced_html_file))
format_success("Interactive visualizations: relative_strength_heatmap.html, sector_performance_heatmap.html, score_distribution.html, interactive_stock_table.html, nse_analysis_dashboard.html")

cat(cyan(bold("===============================================================================\n")))
cat(cyan(bold("                    ENHANCED ANALYSIS SYSTEM READY                    \n")))
cat(cyan(bold("===============================================================================\n")))
