#!/usr/bin/env Rscript

# =============================================================================
# Test 1-Month Change Calculation
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
})

cat("Testing 1-month change calculation with actual data...\n")

# Read the data
data <- read.csv('nse_sec_full_data.csv')

# Get unique dates
dates <- unique(data$TIMESTAMP)
latest_date <- max(dates)
cat("Latest date:", latest_date, "\n")

# Test with a few stocks
test_stocks <- c("20MICRONS", "RELIANCE", "TCS", "INFY", "HDFCBANK")

for(symbol in test_stocks) {
  cat("\n=== Testing", symbol, "===\n")
  
  # Get stock data
  stock_data <- data[data$SYMBOL == symbol, ]
  
  if(nrow(stock_data) == 0) {
    cat("No data found for", symbol, "\n")
    next
  }
  
  # Get latest price
  latest_data <- stock_data[stock_data$TIMESTAMP == latest_date, ]
  current_price <- latest_data$CLOSE
  
  # Calculate 30 days ago
  latest_date_obj <- as.Date(latest_date)
  month_1_ago <- latest_date_obj - 30
  
  # Find closest available date
  available_dates <- unique(stock_data$TIMESTAMP)
  available_dates_obj <- as.Date(available_dates)
  date_diffs <- abs(available_dates_obj - month_1_ago)
  closest_date_idx <- which.min(date_diffs)
  closest_date <- available_dates[closest_date_idx]
  
  cat("Current price:", current_price, "\n")
  cat("Target date (30 days ago):", as.character(month_1_ago), "\n")
  cat("Closest available date:", closest_date, "\n")
  cat("Difference in days:", date_diffs[closest_date_idx], "\n")
  
  # Get month ago price
  month_ago_data <- stock_data[stock_data$TIMESTAMP == closest_date, ]
  month_ago_price <- month_ago_data$CLOSE
  
  # Calculate change
  if(!is.na(month_ago_price) && month_ago_price > 0) {
    change_1m <- ((current_price - month_ago_price) / month_ago_price) * 100
    cat("Month ago price:", month_ago_price, "\n")
    cat("1-month change:", round(change_1m, 2), "%\n")
  } else {
    cat("Month ago price: NA or 0\n")
    cat("1-month change: NA\n")
  }
}

cat("\n=== Summary ===\n")
cat("The 1-month change calculation should work correctly.\n")
cat("If values are showing as NA in the dashboard, the issue is in the analysis script logic.\n")






