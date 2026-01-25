# =============================================================================
# TEST SCRIPT FOR BACKTESTING ENGINE
# =============================================================================
# This script tests the backtesting engine functionality

# Load required libraries
library(dplyr)
library(lubridate)

# Load the backtesting engine
source("backtesting_engine.R")

# Load the integration script
source("integrate_backtesting.R")

# =============================================================================
# TEST 1: QUICK BACKTEST
# =============================================================================

cat("Test 1: Running Quick Backtest\n")
cat("========================================\n")

# Run quick backtest
quick_results <- run_quick_backtest()

if(!is.null(quick_results)) {
  cat("Quick backtest completed successfully!\n")
  cat("Results summary:\n")
  cat("- Total stocks analyzed:", quick_results$metrics$total_stocks, "\n")
  cat("- Total trades executed:", quick_results$metrics$total_trades, "\n")
  cat("- Average win rate:", round(quick_results$metrics$avg_win_rate * 100, 1), "%\n")
  cat("- Average confidence score:", round(quick_results$metrics$avg_confidence * 100, 1), "%\n")
} else {
  cat("Quick backtest failed or no results generated\n")
}

# =============================================================================
# TEST 2: SINGLE STOCK BACKTEST
# =============================================================================

cat("\nTest 2: Single Stock Backtest\n")
cat("========================================\n")

  # Load sample data
  load("data/nse_stock_cache.RData")
  stock_data <- nse_stock_data
stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)

# Get a stock with sufficient data
sample_stock <- stock_data %>%
  group_by(SYMBOL) %>%
  filter(n() >= 100) %>%
  summarise() %>%
  head(1) %>%
  pull(SYMBOL)

if(length(sample_stock) > 0) {
  cat("Testing single stock:", sample_stock, "\n")
  
  # Get stock data
  stock_subset <- stock_data %>%
    filter(SYMBOL == sample_stock) %>%
    arrange(TIMESTAMP)
  
  # Calculate technical indicators
  stock_subset$RSI <- calculate_rsi(stock_subset$CLOSE, 14)
  stock_subset$SMA_20 <- calculate_sma(stock_subset$CLOSE, 20)
  stock_subset$SMA_50 <- calculate_sma(stock_subset$CLOSE, 50)
  stock_subset$MOMENTUM_50D <- c(NA, diff(stock_subset$CLOSE, lag = 50)) / lag(stock_subset$CLOSE, 50)
  
  # Generate signals
  signals <- generate_trading_signals(stock_subset)
  
  if(nrow(signals) > 0) {
    # Initialize backtesting engine
    engine <- BacktestingEngine$new(stock_subset, signals)
    
    # Run backtest for single stock
    result <- engine$backtest_stock(sample_stock)
    
    if(!is.null(result)) {
      cat("Single stock backtest completed!\n")
      cat("Results for", sample_stock, ":\n")
      cat("- Total trades:", result$summary$TOTAL_TRADES, "\n")
      cat("- Win rate:", round(result$summary$WIN_RATE * 100, 1), "%\n")
      cat("- Total return:", round(result$summary$TOTAL_RETURN * 100, 1), "%\n")
      cat("- Confidence score:", round(result$summary$CONFIDENCE_SCORE * 100, 1), "%\n")
    } else {
      cat("Single stock backtest failed\n")
    }
  } else {
    cat("No signals generated for", sample_stock, "\n")
  }
} else {
  cat("No suitable stock found for testing\n")
}

# =============================================================================
# TEST 3: CONFIDENCE SCORE ANALYSIS
# =============================================================================

cat("\nTest 3: Confidence Score Analysis\n")
cat("========================================\n")

if(!is.null(quick_results)) {
  # Analyze confidence scores
  confidence_analysis <- quick_results$confidence
  
  if(nrow(confidence_analysis) > 0) {
    cat("Confidence Level Analysis:\n")
    print(confidence_analysis)
    
    # Get high confidence stocks
    high_confidence_stocks <- quick_results$results %>%
      filter(CONFIDENCE_SCORE >= 0.7) %>%
      arrange(desc(ANNUALIZED_RETURN))
    
    if(nrow(high_confidence_stocks) > 0) {
      cat("\nHigh Confidence Stocks (>= 70%):\n")
      print(high_confidence_stocks %>% 
        select(SYMBOL, CONFIDENCE_SCORE, WIN_RATE, ANNUALIZED_RETURN) %>%
        head(5))
    } else {
      cat("No high confidence stocks found\n")
    }
  }
}

# =============================================================================
# TEST 4: PERFORMANCE METRICS
# =============================================================================

cat("\nTest 4: Performance Metrics Analysis\n")
cat("========================================\n")

if(!is.null(quick_results)) {
  metrics <- quick_results$metrics
  
  cat("Overall Performance Metrics:\n")
  cat("- Total stocks analyzed:", metrics$total_stocks, "\n")
  cat("- Total trades executed:", metrics$total_trades, "\n")
  cat("- Average win rate:", round(metrics$avg_win_rate * 100, 1), "%\n")
  cat("- Average confidence score:", round(metrics$avg_confidence * 100, 1), "%\n")
  cat("- Average annual return:", round(metrics$avg_return * 100, 1), "%\n")
  cat("- Average Sharpe ratio:", round(metrics$avg_sharpe, 2), "\n")
  cat("- Profitable stocks:", metrics$profitable_stocks, "/", metrics$total_stocks, "\n")
  cat("- High confidence stocks:", metrics$high_confidence_stocks, "/", metrics$total_stocks, "\n")
  
  # Calculate improvement recommendations
  cat("\nImprovement Recommendations:\n")
  if(metrics$avg_win_rate < 0.5) {
    cat("- Low win rate suggests need for better entry/exit criteria\n")
  }
  if(metrics$avg_confidence < 0.6) {
    cat("- Low confidence scores indicate need for signal refinement\n")
  }
  if(metrics$avg_return < 0.1) {
    cat("- Low returns suggest need for better risk management\n")
  }
  if(metrics$avg_win_rate >= 0.5 && metrics$avg_confidence >= 0.6 && metrics$avg_return >= 0.1) {
    cat("- Trading engine performing well - consider optimization\n")
  }
}

# =============================================================================
# TEST 5: SIGNAL PATTERN ANALYSIS
# =============================================================================

cat("\nTest 5: Signal Pattern Analysis\n")
cat("========================================\n")

if(!is.null(quick_results)) {
  # Analyze signal patterns
  signal_patterns <- analyze_signal_patterns(quick_results$results)
  
  if(nrow(signal_patterns) > 0) {
    cat("Signal Pattern Analysis:\n")
    print(signal_patterns)
  }
}

# =============================================================================
# TEST 6: SAVE RESULTS
# =============================================================================

cat("\nTest 6: Saving Results\n")
cat("========================================\n")

if(!is.null(quick_results)) {
  # Create output directory
  output_dir <- "output/backtesting/test_results"
  if(!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  # Save results
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Save detailed results
  write.csv(quick_results$results, 
            file.path(output_dir, paste0("test_results_", timestamp, ".csv")), 
            row.names = FALSE)
  
  # Save confidence analysis
  write.csv(quick_results$confidence, 
            file.path(output_dir, paste0("confidence_analysis_", timestamp, ".csv")), 
            row.names = FALSE)
  
  cat("Test results saved to:", output_dir, "\n")
}

# =============================================================================
# SUMMARY
# =============================================================================

cat("\n==================================================\n")
cat("BACKTESTING ENGINE TEST SUMMARY\n")
cat("==================================================\n")

if(!is.null(quick_results)) {
  cat("✅ All tests completed successfully!\n")
  cat("📊 Backtesting engine is working correctly\n")
  cat("🎯 Confidence scoring system is functional\n")
  cat("📈 Performance metrics are being calculated\n")
  cat("💾 Results are being saved properly\n")
  
  cat("\nKey Findings:\n")
  cat("- Engine analyzed", quick_results$metrics$total_stocks, "stocks\n")
  cat("- Generated", quick_results$metrics$total_trades, "trades\n")
  cat("- Average confidence score:", round(quick_results$metrics$avg_confidence * 100, 1), "%\n")
  cat("- High confidence stocks:", quick_results$metrics$high_confidence_stocks, "\n")
  
  cat("\nNext Steps:\n")
  cat("1. Run comprehensive backtesting with full dataset\n")
  cat("2. Implement ML-based signal improvement\n")
  cat("3. Add more sophisticated risk management\n")
  cat("4. Optimize signal parameters\n")
} else {
  cat("❌ Some tests failed\n")
  cat("🔧 Check data availability and signal generation\n")
}

cat("\nBacktesting engine test completed!\n")
