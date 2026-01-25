# =============================================================================
# SAVE BACKTESTING RESULTS AND CONFIDENCE SCORES
# =============================================================================
# This script saves backtesting results and confidence scores to CSV files

library(dplyr)
library(lubridate)

# =============================================================================
# FUNCTIONS
# =============================================================================

# Function to load and combine all backtesting results
load_backtesting_results <- function() {
  cat("Loading backtesting results...\n")
  
  # Check for quick backtesting results
  quick_results_files <- list.files("reports/backtesting", 
                                   pattern = "quick_backtest_results_.*\\.csv$", 
                                   full.names = TRUE)
  
  if(length(quick_results_files) > 0) {
    # Load the latest quick backtesting results
    latest_quick <- quick_results_files[length(quick_results_files)]
    cat("Loading quick backtesting results from:", latest_quick, "\n")
    
    quick_results <- read.csv(latest_quick, stringsAsFactors = FALSE)
    cat("Loaded", nrow(quick_results), "quick backtesting results\n")
    
    return(list(
      type = "quick",
      data = quick_results,
      source_file = latest_quick
    ))
  }
  
  # Check for historical backtesting results
  historical_results_files <- list.files("reports/backtesting", 
                                        pattern = "historical_backtest_results_.*\\.csv$", 
                                        full.names = TRUE)
  
  if(length(historical_results_files) > 0) {
    # Load the latest historical backtesting results
    latest_historical <- historical_results_files[length(historical_results_files)]
    cat("Loading historical backtesting results from:", latest_historical, "\n")
    
    historical_results <- read.csv(latest_historical, stringsAsFactors = FALSE)
    cat("Loaded", nrow(historical_results), "historical backtesting results\n")
    
    return(list(
      type = "historical",
      data = historical_results,
      source_file = latest_historical
    ))
  }
  
  cat("No backtesting results found. Running quick backtesting analysis...\n")
  
  # Run quick backtesting if no results exist
  source('quick_real_backtesting.R')
  results <- run_quick_real_backtesting()
  
  if(!is.null(results)) {
    return(list(
      type = "quick",
      data = results,
      source_file = "generated"
    ))
  }
  
  return(NULL)
}

# Function to create comprehensive results summary
create_comprehensive_results <- function(backtesting_data) {
  cat("Creating comprehensive results summary...\n")
  
  if(is.null(backtesting_data)) {
    cat("No backtesting data available\n")
    return(NULL)
  }
  
  # Get the data
  data <- backtesting_data$data
  
  # Create comprehensive results
  comprehensive_results <- data %>%
    select(
      SYMBOL,
      TRADING_SIGNAL,
      TECHNICAL_SCORE,
      RSI,
      RELATIVE_STRENGTH,
      CONFIDENCE_SCORE,
      SIMULATED_WIN_RATE,
      SIMULATED_RETURN,
      SIMULATED_TRADES,
      RISK_ADJUSTED_RETURN
    ) %>%
    mutate(
      # Add confidence categories
      CONFIDENCE_CATEGORY = case_when(
        CONFIDENCE_SCORE >= 0.8 ~ "Very High",
        CONFIDENCE_SCORE >= 0.6 ~ "High",
        CONFIDENCE_SCORE >= 0.4 ~ "Medium",
        TRUE ~ "Low"
      ),
      
      # Add performance categories
      PERFORMANCE_CATEGORY = case_when(
        SIMULATED_RETURN >= 0.15 ~ "Excellent",
        SIMULATED_RETURN >= 0.10 ~ "Good",
        SIMULATED_RETURN >= 0.05 ~ "Moderate",
        SIMULATED_RETURN >= 0 ~ "Poor",
        TRUE ~ "Negative"
      ),
      
      # Add risk-adjusted performance
      RISK_PERFORMANCE = case_when(
        RISK_ADJUSTED_RETURN >= 0.2 ~ "Excellent",
        RISK_ADJUSTED_RETURN >= 0.1 ~ "Good",
        RISK_ADJUSTED_RETURN >= 0.05 ~ "Moderate",
        RISK_ADJUSTED_RETURN >= 0 ~ "Poor",
        TRUE ~ "Negative"
      ),
      
      # Add timestamp
      ANALYSIS_DATE = Sys.Date(),
      BACKTESTING_TYPE = backtesting_data$type
    ) %>%
    arrange(desc(CONFIDENCE_SCORE), desc(SIMULATED_RETURN))
  
  return(comprehensive_results)
}

# Function to create confidence score summary
create_confidence_summary <- function(comprehensive_results) {
  cat("Creating confidence score summary...\n")
  
  if(is.null(comprehensive_results)) {
    return(NULL)
  }
  
  # Create confidence score summary
  confidence_summary <- comprehensive_results %>%
    group_by(CONFIDENCE_CATEGORY) %>%
    summarise(
      COUNT = n(),
      AVG_CONFIDENCE = mean(CONFIDENCE_SCORE, na.rm = TRUE),
      AVG_WIN_RATE = mean(SIMULATED_WIN_RATE, na.rm = TRUE),
      AVG_RETURN = mean(SIMULATED_RETURN, na.rm = TRUE),
      AVG_RISK_ADJUSTED = mean(RISK_ADJUSTED_RETURN, na.rm = TRUE),
      STRONG_BUY_COUNT = sum(TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE),
      BUY_COUNT = sum(TRADING_SIGNAL == "BUY", na.rm = TRUE),
      SELL_COUNT = sum(TRADING_SIGNAL == "SELL", na.rm = TRUE),
      STRONG_SELL_COUNT = sum(TRADING_SIGNAL == "STRONG_SELL", na.rm = TRUE),
      .groups = 'drop'
    ) %>%
    arrange(desc(AVG_CONFIDENCE))
  
  return(confidence_summary)
}

# Function to create top performers summary
create_top_performers <- function(comprehensive_results) {
  cat("Creating top performers summary...\n")
  
  if(is.null(comprehensive_results)) {
    return(NULL)
  }
  
  # Top performers by confidence score
  top_confidence <- comprehensive_results %>%
    filter(CONFIDENCE_SCORE >= 0.7) %>%
    head(20) %>%
    select(SYMBOL, TRADING_SIGNAL, TECHNICAL_SCORE, CONFIDENCE_SCORE, 
           SIMULATED_RETURN, RISK_ADJUSTED_RETURN, CONFIDENCE_CATEGORY)
  
  # Top performers by return
  top_return <- comprehensive_results %>%
    filter(SIMULATED_RETURN > 0) %>%
    arrange(desc(SIMULATED_RETURN)) %>%
    head(20) %>%
    select(SYMBOL, TRADING_SIGNAL, TECHNICAL_SCORE, CONFIDENCE_SCORE, 
           SIMULATED_RETURN, RISK_ADJUSTED_RETURN, PERFORMANCE_CATEGORY)
  
  # Top performers by risk-adjusted return
  top_risk_adjusted <- comprehensive_results %>%
    filter(RISK_ADJUSTED_RETURN > 0) %>%
    arrange(desc(RISK_ADJUSTED_RETURN)) %>%
    head(20) %>%
    select(SYMBOL, TRADING_SIGNAL, TECHNICAL_SCORE, CONFIDENCE_SCORE, 
           SIMULATED_RETURN, RISK_ADJUSTED_RETURN, RISK_PERFORMANCE)
  
  return(list(
    top_confidence = top_confidence,
    top_return = top_return,
    top_risk_adjusted = top_risk_adjusted
  ))
}

# Function to save results to CSV files
save_results_to_csv <- function(comprehensive_results, confidence_summary, top_performers) {
  cat("Saving results to CSV files...\n")
  
  # Create output directory
  output_dir <- "output/backtesting_results"
  if(!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Save comprehensive results
  comprehensive_file <- file.path(output_dir, paste0("comprehensive_backtesting_results_", timestamp, ".csv"))
  write.csv(comprehensive_results, comprehensive_file, row.names = FALSE)
  cat("✓ Saved comprehensive results to:", comprehensive_file, "\n")
  
  # Save confidence summary
  confidence_file <- file.path(output_dir, paste0("confidence_summary_", timestamp, ".csv"))
  write.csv(confidence_summary, confidence_file, row.names = FALSE)
  cat("✓ Saved confidence summary to:", confidence_file, "\n")
  
  # Save top performers
  if(!is.null(top_performers)) {
    top_confidence_file <- file.path(output_dir, paste0("top_confidence_performers_", timestamp, ".csv"))
    write.csv(top_performers$top_confidence, top_confidence_file, row.names = FALSE)
    cat("✓ Saved top confidence performers to:", top_confidence_file, "\n")
    
    top_return_file <- file.path(output_dir, paste0("top_return_performers_", timestamp, ".csv"))
    write.csv(top_performers$top_return, top_return_file, row.names = FALSE)
    cat("✓ Saved top return performers to:", top_return_file, "\n")
    
    top_risk_file <- file.path(output_dir, paste0("top_risk_adjusted_performers_", timestamp, ".csv"))
    write.csv(top_performers$top_risk_adjusted, top_risk_file, row.names = FALSE)
    cat("✓ Saved top risk-adjusted performers to:", top_risk_file, "\n")
  }
  
  # Create a summary file with key statistics
  summary_stats <- data.frame(
    METRIC = c(
      "Total Stocks Analyzed",
      "High Confidence Stocks (≥70%)",
      "Very High Confidence Stocks (≥80%)",
      "Average Confidence Score",
      "Average Simulated Return",
      "Average Win Rate",
      "Strong Buy Signals",
      "Buy Signals",
      "Sell Signals",
      "Strong Sell Signals"
    ),
    VALUE = c(
      nrow(comprehensive_results),
      sum(comprehensive_results$CONFIDENCE_SCORE >= 0.7, na.rm = TRUE),
      sum(comprehensive_results$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE),
      round(mean(comprehensive_results$CONFIDENCE_SCORE, na.rm = TRUE) * 100, 2),
      round(mean(comprehensive_results$SIMULATED_RETURN, na.rm = TRUE) * 100, 2),
      round(mean(comprehensive_results$SIMULATED_WIN_RATE, na.rm = TRUE) * 100, 2),
      sum(comprehensive_results$TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE),
      sum(comprehensive_results$TRADING_SIGNAL == "BUY", na.rm = TRUE),
      sum(comprehensive_results$TRADING_SIGNAL == "SELL", na.rm = TRUE),
      sum(comprehensive_results$TRADING_SIGNAL == "STRONG_SELL", na.rm = TRUE)
    ),
    UNIT = c(
      "stocks",
      "stocks",
      "stocks",
      "%",
      "%",
      "%",
      "signals",
      "signals",
      "signals",
      "signals"
    )
  )
  
  summary_file <- file.path(output_dir, paste0("backtesting_summary_stats_", timestamp, ".csv"))
  write.csv(summary_stats, summary_file, row.names = FALSE)
  cat("✓ Saved summary statistics to:", summary_file, "\n")
  
  return(list(
    comprehensive_file = comprehensive_file,
    confidence_file = confidence_file,
    summary_file = summary_file,
    output_dir = output_dir
  ))
}

# Function to print summary
print_summary <- function(comprehensive_results, confidence_summary, saved_files) {
  cat("\n" , "=", 60, "\n")
  cat("BACKTESTING RESULTS SAVED SUCCESSFULLY\n")
  cat("=", 60, "\n")
  
  cat("\n📊 SUMMARY STATISTICS:\n")
  cat("Total Stocks Analyzed:", nrow(comprehensive_results), "\n")
  cat("Average Confidence Score:", round(mean(comprehensive_results$CONFIDENCE_SCORE, na.rm = TRUE) * 100, 1), "%\n")
  cat("High Confidence Stocks (≥70%):", sum(comprehensive_results$CONFIDENCE_SCORE >= 0.7, na.rm = TRUE), "\n")
  cat("Very High Confidence Stocks (≥80%):", sum(comprehensive_results$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE), "\n")
  cat("Average Simulated Return:", round(mean(comprehensive_results$SIMULATED_RETURN, na.rm = TRUE) * 100, 1), "%\n")
  cat("Average Win Rate:", round(mean(comprehensive_results$SIMULATED_WIN_RATE, na.rm = TRUE) * 100, 1), "%\n")
  
  cat("\n📈 CONFIDENCE DISTRIBUTION:\n")
  print(confidence_summary)
  
  cat("\n💾 FILES SAVED:\n")
  cat("Comprehensive Results:", saved_files$comprehensive_file, "\n")
  cat("Confidence Summary:", saved_files$confidence_file, "\n")
  cat("Summary Statistics:", saved_files$summary_file, "\n")
  cat("Output Directory:", saved_files$output_dir, "\n")
  
  cat("\n🎯 TOP 5 HIGH CONFIDENCE STOCKS:\n")
  top_5 <- comprehensive_results %>%
    filter(CONFIDENCE_SCORE >= 0.7) %>%
    head(5) %>%
    select(SYMBOL, TRADING_SIGNAL, CONFIDENCE_SCORE, SIMULATED_RETURN)
  print(top_5)
  
  cat("\n" , "=", 60, "\n")
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

save_backtesting_results_to_csv <- function() {
  cat("Starting to save backtesting results and confidence scores...\n")
  cat("============================================================\n")
  
  # Step 1: Load backtesting results
  backtesting_data <- load_backtesting_results()
  if(is.null(backtesting_data)) {
    cat("Failed to load backtesting results\n")
    return(NULL)
  }
  
  # Step 2: Create comprehensive results
  comprehensive_results <- create_comprehensive_results(backtesting_data)
  if(is.null(comprehensive_results)) {
    cat("Failed to create comprehensive results\n")
    return(NULL)
  }
  
  # Step 3: Create confidence summary
  confidence_summary <- create_confidence_summary(comprehensive_results)
  
  # Step 4: Create top performers
  top_performers <- create_top_performers(comprehensive_results)
  
  # Step 5: Save to CSV files
  saved_files <- save_results_to_csv(comprehensive_results, confidence_summary, top_performers)
  
  # Step 6: Print summary
  print_summary(comprehensive_results, confidence_summary, saved_files)
  
  return(saved_files)
}

# =============================================================================
# EXECUTION
# =============================================================================

cat("Backtesting results save script loaded successfully!\n")
cat("Use save_backtesting_results_to_csv() to save results\n")

# Run the save operation if called directly
if(interactive()) {
  cat("Saving backtesting results and confidence scores...\n")
  results <- save_backtesting_results_to_csv()
  
  if(!is.null(results)) {
    cat("\n✅ Backtesting results saved successfully!\n")
    cat("Check the output/backtesting_results/ directory for CSV files.\n")
  } else {
    cat("\n❌ Failed to save backtesting results.\n")
  }
}
