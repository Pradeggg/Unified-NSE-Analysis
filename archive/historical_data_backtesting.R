# =============================================================================
# HISTORICAL DATA BACKTESTING - NSE TRADING SIGNALS
# =============================================================================
# This script loads historical data from nse_sec_full_data.csv and runs backtesting

library(dplyr)
library(lubridate)
library(readr)

# Load the backtesting engine
source("backtesting_engine.R")

# =============================================================================
# DATA LOADING AND PREPARATION
# =============================================================================

# Function to load historical data from nse_sec_full_data.csv
load_historical_data <- function() {
  cat("Loading historical data from nse_sec_full_data.csv...\n")
  
  # Check if the file exists in various locations
  possible_paths <- c(
    "NSE-index/nse_sec_full_data.csv",
    "nse_sec_full_data.csv",
    "../NSE-index/nse_sec_full_data.csv",
    "data/nse_sec_full_data.csv"
  )
  
  file_path <- NULL
  for(path in possible_paths) {
    if(file.exists(path)) {
      file_path <- path
      break
    }
  }
  
  if(is.null(file_path)) {
    cat("Error: nse_sec_full_data.csv not found in any of these locations:\n")
    cat("  - NSE-index/nse_sec_full_data.csv\n")
    cat("  - nse_sec_full_data.csv\n")
    cat("  - ../NSE-index/nse_sec_full_data.csv\n")
    cat("  - data/nse_sec_full_data.csv\n")
    return(NULL)
  }
  
  cat("Using historical data file:", file_path, "\n")
  
  # Load the historical data
  tryCatch({
    historical_data <- read.csv(file_path, 
                               stringsAsFactors = FALSE, 
                               fileEncoding = "UTF-8")
    
    cat("Successfully loaded historical data\n")
    cat("Total records:", nrow(historical_data), "\n")
    cat("Columns:", paste(colnames(historical_data), collapse = ", "), "\n")
    cat("Date range:", min(historical_data$TIMESTAMP, na.rm = TRUE), "to", 
        max(historical_data$TIMESTAMP, na.rm = TRUE), "\n")
    cat("Unique stocks:", length(unique(historical_data$SYMBOL)), "\n")
    
    return(historical_data)
    
  }, error = function(e) {
    cat("Error loading historical data:", e$message, "\n")
    return(NULL)
  })
}

# Function to load latest analysis results
load_latest_analysis <- function() {
  cat("Loading latest analysis results...\n")
  
  # Find the latest CSV file
  csv_files <- list.files("reports", pattern = "comprehensive_nse_enhanced_.*\\.csv$", full.names = TRUE)
  if(length(csv_files) == 0) {
    cat("No analysis results found!\n")
    return(NULL)
  }
  
  latest_csv <- csv_files[length(csv_files)]
  cat("Using:", latest_csv, "\n")
  
  # Load the analysis results
  analysis_results <- read.csv(latest_csv, stringsAsFactors = FALSE)
  
  cat("Loaded", nrow(analysis_results), "stocks from analysis\n")
  return(analysis_results)
}

# Function to prepare historical data for backtesting
prepare_historical_data_for_backtesting <- function(historical_data, analysis_results) {
  cat("Preparing historical data for backtesting...\n")
  
  # Get stocks with trading signals
  signal_stocks <- analysis_results %>%
    filter(TRADING_SIGNAL %in% c("BUY", "SELL", "STRONG_BUY", "STRONG_SELL")) %>%
    pull(SYMBOL)
  
  cat("Found", length(signal_stocks), "stocks with trading signals\n")
  
  # Filter historical data for stocks with signals
  filtered_data <- historical_data %>%
    filter(SYMBOL %in% signal_stocks) %>%
    arrange(SYMBOL, TIMESTAMP)
  
  # Convert TIMESTAMP to Date if needed
  if(is.character(filtered_data$TIMESTAMP)) {
    filtered_data$TIMESTAMP <- as.Date(filtered_data$TIMESTAMP)
  }
  
  # Map column names if needed
  if("TOTTRDQTY" %in% colnames(filtered_data) && !"VOLUME" %in% colnames(filtered_data)) {
    filtered_data$VOLUME <- filtered_data$TOTTRDQTY
    cat("Mapped TOTTRDQTY to VOLUME\n")
  }
  
  # Ensure required columns exist
  required_cols <- c("SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME")
  missing_cols <- setdiff(required_cols, colnames(filtered_data))
  
  if(length(missing_cols) > 0) {
    cat("Missing columns:", paste(missing_cols, collapse = ", "), "\n")
    cat("Available columns:", paste(colnames(filtered_data), collapse = ", "), "\n")
    cat("Attempting to map available columns...\n")
    
    # Try to map LAST to CLOSE if CLOSE is missing
    if("LAST" %in% colnames(filtered_data) && !"CLOSE" %in% colnames(filtered_data)) {
      filtered_data$CLOSE <- filtered_data$LAST
      cat("Mapped LAST to CLOSE\n")
    }
    
    # Recheck missing columns
    missing_cols <- setdiff(required_cols, colnames(filtered_data))
    if(length(missing_cols) > 0) {
      cat("Still missing columns:", paste(missing_cols, collapse = ", "), "\n")
      return(NULL)
    }
  }
  
  # Filter for stocks with sufficient data (at least 6 months)
  sufficient_data <- filtered_data %>%
    group_by(SYMBOL) %>%
    filter(n() >= 120) %>%  # At least 120 trading days
    ungroup()
  
  cat("Prepared historical data for", length(unique(sufficient_data$SYMBOL)), "stocks\n")
  cat("Total records:", nrow(sufficient_data), "\n")
  
  return(sufficient_data)
}

# Function to extract trading signals from analysis
extract_trading_signals <- function(analysis_results) {
  cat("Extracting trading signals from analysis...\n")
  
  # Filter for stocks with trading signals
  trading_signals <- analysis_results %>%
    filter(TRADING_SIGNAL %in% c("BUY", "SELL", "STRONG_BUY", "STRONG_SELL")) %>%
    select(
      SYMBOL,
      TRADING_SIGNAL,
      TECHNICAL_SCORE,
      RSI,
      RELATIVE_STRENGTH,
      TREND_SIGNAL
    )
  
  # Add timestamp (using latest date from analysis)
  latest_date <- max(as.Date(analysis_results$TIMESTAMP, format="%Y-%m-%d"), na.rm = TRUE)
  trading_signals$TIMESTAMP <- latest_date
  
  # Add momentum and volume ratio (simplified for now)
  trading_signals$MOMENTUM_50D <- trading_signals$RELATIVE_STRENGTH / 100
  trading_signals$VOLUME_RATIO <- 1.0
  
  cat("Extracted", nrow(trading_signals), "trading signals\n")
  cat("Signal distribution:\n")
  print(table(trading_signals$TRADING_SIGNAL))
  
  return(trading_signals)
}

# Function to generate historical signals for backtesting
generate_historical_signals <- function(historical_data, trading_signals) {
  cat("Generating historical signals for backtesting...\n")
  
  # Get the list of stocks with current signals
  signal_stocks <- unique(trading_signals$SYMBOL)
  
  historical_signals <- data.frame()
  
  for(stock in signal_stocks) {
    cat("Processing signals for:", stock, "\n")
    
    # Get stock data
    stock_subset <- historical_data %>%
      filter(SYMBOL == stock) %>%
      arrange(TIMESTAMP)
    
    if(nrow(stock_subset) < 50) next
    
    # Calculate technical indicators
    stock_subset$RSI <- calculate_rsi(stock_subset$CLOSE, 14)
    stock_subset$SMA_20 <- calculate_sma(stock_subset$CLOSE, 20)
    stock_subset$SMA_50 <- calculate_sma(stock_subset$CLOSE, 50)
    stock_subset$MOMENTUM_50D <- c(NA, diff(stock_subset$CLOSE, lag = 50)) / lag(stock_subset$CLOSE, 50)
    
    # Get current signal for this stock
    current_signal <- trading_signals %>%
      filter(SYMBOL == stock) %>%
      head(1)
    
    if(nrow(current_signal) == 0) next
    
    # Generate historical signals based on current signal type
    signals <- generate_stock_signals(stock_subset, current_signal$TRADING_SIGNAL)
    
    if(nrow(signals) > 0) {
      historical_signals <- rbind(historical_signals, signals)
    }
  }
  
  cat("Generated", nrow(historical_signals), "historical signals\n")
  return(historical_signals)
}

# Function to calculate RSI
calculate_rsi <- function(prices, period = 14) {
  if(length(prices) < period + 1) return(rep(NA, length(prices)))
  
  gains <- c(0, pmax(diff(prices), 0))
  losses <- c(0, pmax(-diff(prices), 0))
  
  avg_gain <- cumsum(gains)
  avg_loss <- cumsum(losses)
  
  for(i in (period + 1):length(prices)) {
    avg_gain[i] <- (avg_gain[i-1] * (period - 1) + gains[i]) / period
    avg_loss[i] <- (avg_loss[i-1] * (period - 1) + losses[i]) / period
  }
  
  rs <- avg_gain / avg_loss
  rsi <- 100 - (100 / (1 + rs))
  
  return(rsi)
}

# Function to calculate SMA
calculate_sma <- function(prices, period) {
  if(length(prices) < period) return(rep(NA, length(prices)))
  
  sma <- c(rep(NA, period - 1), 
           sapply(period:length(prices), function(i) mean(prices[(i-period+1):i])))
  
  return(sma)
}

# Function to generate signals for a stock
generate_stock_signals <- function(stock_data, signal_type) {
  signals <- data.frame()
  
  # Determine signal frequency based on signal type
  if(signal_type %in% c("STRONG_BUY", "STRONG_SELL")) {
    # More frequent signals for strong signals
    signal_threshold <- 0.015  # 1.5% change
  } else {
    # Less frequent signals for regular signals
    signal_threshold <- 0.025  # 2.5% change
  }
  
  for(i in 50:nrow(stock_data)) {
    current_data <- stock_data[i, ]
    
    # Skip if missing data
    if(is.na(current_data$RSI) || is.na(current_data$SMA_20) || is.na(current_data$SMA_50)) {
      next
    }
    
    # Calculate price change
    if(i > 1) {
      price_change <- (current_data$CLOSE - stock_data$CLOSE[i-1]) / stock_data$CLOSE[i-1]
    } else {
      next
    }
    
    # Generate signal based on signal type and conditions
    signal <- NULL
    
    if(signal_type %in% c("BUY", "STRONG_BUY")) {
      # Buy conditions
      if(price_change > signal_threshold && 
         current_data$RSI < 70 && 
         current_data$CLOSE > current_data$SMA_20) {
        signal <- "BUY"
      }
    } else if(signal_type %in% c("SELL", "STRONG_SELL")) {
      # Sell conditions
      if(price_change < -signal_threshold && 
         current_data$RSI > 30 && 
         current_data$CLOSE < current_data$SMA_20) {
        signal <- "SELL"
      }
    }
    
    # Add signal if generated
    if(!is.null(signal)) {
      signal_row <- data.frame(
        SYMBOL = current_data$SYMBOL,
        TIMESTAMP = current_data$TIMESTAMP,
        TRADING_SIGNAL = signal,
        RSI = current_data$RSI,
        MOMENTUM_50D = current_data$MOMENTUM_50D,
        VOLUME_RATIO = 1.0,  # Simplified for now
        stringsAsFactors = FALSE
      )
      signals <- rbind(signals, signal_row)
    }
  }
  
  return(signals)
}

# =============================================================================
# MAIN BACKTESTING EXECUTION
# =============================================================================

run_historical_data_backtesting <- function() {
  cat("Starting historical data backtesting analysis...\n")
  cat("============================================================\n")
  
  # Step 1: Load historical data
  historical_data <- load_historical_data()
  if(is.null(historical_data)) {
    cat("Failed to load historical data\n")
    return(NULL)
  }
  
  # Step 2: Load latest analysis results
  analysis_results <- load_latest_analysis()
  if(is.null(analysis_results)) {
    cat("Failed to load analysis results\n")
    return(NULL)
  }
  
  # Step 3: Prepare historical data for backtesting
  prepared_data <- prepare_historical_data_for_backtesting(historical_data, analysis_results)
  if(is.null(prepared_data)) {
    cat("Failed to prepare historical data\n")
    return(NULL)
  }
  
  # Step 4: Extract trading signals from analysis
  trading_signals <- extract_trading_signals(analysis_results)
  if(nrow(trading_signals) == 0) {
    cat("No trading signals found\n")
    return(NULL)
  }
  
  # Step 5: Generate historical signals for backtesting
  historical_signals <- generate_historical_signals(prepared_data, trading_signals)
  if(nrow(historical_signals) == 0) {
    cat("No historical signals generated\n")
    return(NULL)
  }
  
  # Step 6: Run backtesting
  cat("Running backtesting analysis...\n")
  backtest_results <- run_backtesting_analysis(prepared_data, historical_signals)
  
  # Step 7: Generate comprehensive report
  generate_historical_backtesting_report(backtest_results, trading_signals, analysis_results)
  
  return(backtest_results)
}

# Function to generate comprehensive report
generate_historical_backtesting_report <- function(backtest_results, trading_signals, analysis_results) {
  cat("Generating comprehensive historical data backtesting report...\n")
  
  # Create report directory
  report_dir <- "reports/backtesting"
  if(!dir.exists(report_dir)) {
    dir.create(report_dir, recursive = TRUE)
  }
  
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  report_file <- file.path(report_dir, paste0("historical_backtesting_report_", timestamp, ".md"))
  
  # Generate report content
  report_content <- paste0(
    "# Historical Data Backtesting Report\n",
    "Generated: ", Sys.time(), "\n\n",
    
    "## Executive Summary\n",
    "This report presents the results of backtesting our trading signals on real historical NSE data from nse_sec_full_data.csv.\n\n",
    
    "## Backtesting Results\n",
    "- Total Stocks Analyzed: ", backtest_results$metrics$total_stocks, "\n",
    "- Total Trades Executed: ", backtest_results$metrics$total_trades, "\n",
    "- Average Win Rate: ", round(backtest_results$metrics$avg_win_rate * 100, 1), "%\n",
    "- Average Confidence Score: ", round(backtest_results$metrics$avg_confidence * 100, 1), "%\n",
    "- Average Annual Return: ", round(backtest_results$metrics$avg_return * 100, 1), "%\n",
    "- Profitable Stocks: ", backtest_results$metrics$profitable_stocks, "/", backtest_results$metrics$total_stocks, "\n",
    "- High Confidence Stocks: ", backtest_results$metrics$high_confidence_stocks, "/", backtest_results$metrics$total_stocks, "\n\n",
    
    "## Trading Signals Analysis\n",
    "Original signals from analysis:\n",
    "```\n",
    paste(capture.output(print(table(trading_signals$TRADING_SIGNAL))), collapse = "\n"),
    "\n```\n\n",
    
    "## Top Performing Stocks\n",
    "```\n",
    paste(capture.output(print(head(backtest_results$results %>% 
      arrange(desc(CONFIDENCE_SCORE)) %>% 
      select(SYMBOL, CONFIDENCE_SCORE, WIN_RATE, ANNUALIZED_RETURN, TOTAL_TRADES), 10))), collapse = "\n"),
    "\n```\n\n",
    
    "## Performance Analysis\n\n",
    
    "### Win Rate Distribution\n",
    "- High Performers (≥60%): ", sum(backtest_results$results$WIN_RATE >= 0.6, na.rm = TRUE), " stocks\n",
    "- Medium Performers (40-60%): ", sum(backtest_results$results$WIN_RATE >= 0.4 & backtest_results$results$WIN_RATE < 0.6, na.rm = TRUE), " stocks\n",
    "- Low Performers (<40%): ", sum(backtest_results$results$WIN_RATE < 0.4, na.rm = TRUE), " stocks\n\n",
    
    "### Confidence Score Distribution\n",
    "- Very High Confidence (≥80%): ", sum(backtest_results$results$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE), " stocks\n",
    "- High Confidence (60-80%): ", sum(backtest_results$results$CONFIDENCE_SCORE >= 0.6 & backtest_results$results$CONFIDENCE_SCORE < 0.8, na.rm = TRUE), " stocks\n",
    "- Medium Confidence (40-60%): ", sum(backtest_results$results$CONFIDENCE_SCORE >= 0.4 & backtest_results$results$CONFIDENCE_SCORE < 0.6, na.rm = TRUE), " stocks\n",
    "- Low Confidence (<40%): ", sum(backtest_results$results$CONFIDENCE_SCORE < 0.4, na.rm = TRUE), " stocks\n\n",
    
    "## Recommendations\n\n",
    
    "### Immediate Actions\n",
    "1. **Focus on High Confidence Stocks**: Prioritize stocks with confidence scores ≥70%\n",
    "2. **Signal Refinement**: Improve entry/exit criteria for better win rates\n",
    "3. **Risk Management**: Implement position sizing based on confidence scores\n\n",
    
    "### Medium-term Improvements\n",
    "1. **Parameter Optimization**: Use backtesting results to optimize technical indicators\n",
    "2. **Market Regime Detection**: Adapt signals based on market conditions\n",
    "3. **Volume Analysis**: Incorporate volume-based confirmation signals\n\n",
    
    "### Long-term Enhancements\n",
    "1. **Machine Learning Integration**: Train models on historical performance\n",
    "2. **Multi-timeframe Analysis**: Combine daily/weekly/monthly signals\n",
    "3. **Fundamental Integration**: Add fundamental analysis to technical signals\n\n",
    
    "## Next Steps\n",
    "1. Implement the recommended improvements\n",
    "2. Run weekly backtesting to monitor performance\n",
    "3. Continuously optimize based on results\n",
    "4. Expand to include more sophisticated features\n"
  )
  
  # Write report
  writeLines(report_content, report_file)
  cat("Report saved to:", report_file, "\n")
  
  # Save detailed results
  write.csv(backtest_results$results, 
            file.path(report_dir, paste0("historical_backtest_results_", timestamp, ".csv")), 
            row.names = FALSE)
  
  cat("Historical data backtesting analysis completed!\n")
}

# =============================================================================
# EXECUTION
# =============================================================================

cat("Historical data backtesting script loaded successfully!\n")
cat("Use run_historical_data_backtesting() to start backtesting with real historical data\n")

# Run the analysis if called directly
if(interactive()) {
  cat("Running historical data backtesting analysis...\n")
  results <- run_historical_data_backtesting()
  
  if(!is.null(results)) {
    cat("\nHistorical data backtesting completed successfully!\n")
    cat("Check the reports/backtesting/ directory for detailed results.\n")
  } else {
    cat("\nHistorical data backtesting failed. Check the error messages above.\n")
  }
}
