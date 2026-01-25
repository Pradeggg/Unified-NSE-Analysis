#!/usr/bin/env Rscript

# =============================================================================
# Load Latest NSE Data - Stocks and Index
# =============================================================================
# This script loads the latest available NSE stock and index data
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(lubridate)
})

# Set working directory
setwd("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis")

cat("=== LOADING LATEST NSE DATA ===\n")
cat("Date:", format(Sys.Date(), "%B %d, %Y"), "\n\n")

# =============================================================================
# Load Stock Data
# =============================================================================

cat("=== LOADING STOCK DATA ===\n")

# Load stock data from CSV
if(file.exists("data/nse_sec_full_data.csv")) {
  stock_data <- read.csv("data/nse_sec_full_data.csv", stringsAsFactors = FALSE)
  stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)
  
  cat("✅ Stock data loaded successfully\n")
  cat("- Records:", nrow(stock_data), "\n")
  cat("- Date range:", as.character(min(stock_data$TIMESTAMP)), "to", as.character(max(stock_data$TIMESTAMP)), "\n")
  cat("- Unique stocks:", length(unique(stock_data$SYMBOL)), "\n")
  cat("- Latest date:", as.character(max(stock_data$TIMESTAMP)), "\n")
  
  # Show sample of recent data
  recent_stocks <- stock_data %>%
    filter(TIMESTAMP == max(TIMESTAMP)) %>%
    arrange(desc(TOTTRDQTY)) %>%
    head(10)
  
  cat("\nTop 10 stocks by volume on latest date:\n")
  print(recent_stocks[, c("SYMBOL", "CLOSE", "TOTTRDQTY")])
  
} else {
  cat("❌ Stock data file not found\n")
  stock_data <- NULL
}

# =============================================================================
# Load Index Data
# =============================================================================

cat("\n=== LOADING INDEX DATA ===\n")

# Load index data from CSV
if(file.exists("data/nse_index_data.csv")) {
  index_data <- read.csv("data/nse_index_data.csv", stringsAsFactors = FALSE)
  index_data$TIMESTAMP <- as.Date(index_data$TIMESTAMP)
  
  cat("✅ Index data loaded successfully\n")
  cat("- Records:", nrow(index_data), "\n")
  cat("- Date range:", as.character(min(index_data$TIMESTAMP)), "to", as.character(max(index_data$TIMESTAMP)), "\n")
  cat("- Unique indices:", length(unique(index_data$SYMBOL)), "\n")
  cat("- Latest date:", as.character(max(index_data$TIMESTAMP)), "\n")
  
  # Show sample of recent data
  recent_indices <- index_data %>%
    filter(TIMESTAMP == max(TIMESTAMP)) %>%
    arrange(desc(TOTTRDQTY)) %>%
    head(10)
  
  cat("\nTop 10 indices by volume on latest date:\n")
  print(recent_indices[, c("SYMBOL", "CLOSE", "TOTTRDQTY")])
  
} else {
  cat("❌ Index data file not found\n")
  index_data <- NULL
}

# =============================================================================
# Data Quality Check
# =============================================================================

cat("\n=== DATA QUALITY CHECK ===\n")

if(!is.null(stock_data)) {
  # Check for missing values
  missing_close <- sum(is.na(stock_data$CLOSE))
  missing_symbol <- sum(is.na(stock_data$SYMBOL) | stock_data$SYMBOL == "")
  
  cat("Stock Data Quality:\n")
  cat("- Missing CLOSE prices:", missing_close, "\n")
  cat("- Missing SYMBOLs:", missing_symbol, "\n")
  cat("- Data completeness:", round((1 - (missing_close + missing_symbol) / (nrow(stock_data) * 2)) * 100, 2), "%\n")
}

if(!is.null(index_data)) {
  # Check for missing values
  missing_close <- sum(is.na(index_data$CLOSE))
  missing_symbol <- sum(is.na(index_data$SYMBOL) | index_data$SYMBOL == "")
  
  cat("\nIndex Data Quality:\n")
  cat("- Missing CLOSE prices:", missing_close, "\n")
  cat("- Missing SYMBOLs:", missing_symbol, "\n")
  cat("- Data completeness:", round((1 - (missing_close + missing_symbol) / (nrow(index_data) * 2)) * 100, 2), "%\n")
}

# =============================================================================
# Save to Global Environment
# =============================================================================

# Make data available globally
if(!is.null(stock_data)) {
  assign("nse_stock_data", stock_data, envir = .GlobalEnv)
  cat("\n✅ Stock data loaded to global environment as 'nse_stock_data'\n")
}

if(!is.null(index_data)) {
  assign("nse_index_data", index_data, envir = .GlobalEnv)
  cat("✅ Index data loaded to global environment as 'nse_index_data'\n")
}

# =============================================================================
# Summary
# =============================================================================

cat("\n=== FINAL SUMMARY ===\n")
cat("✅ NSE data loading completed successfully!\n")
cat("📊 Data is now available for analysis\n")
cat("🔄 Use 'nse_stock_data' and 'nse_index_data' variables in your analysis\n")

# Show data structure
if(!is.null(stock_data)) {
  cat("\nStock data structure:\n")
  str(stock_data, max.level = 1)
}

if(!is.null(index_data)) {
  cat("\nIndex data structure:\n")
  str(index_data, max.level = 1)
}

cat("\n=== END OF DATA LOADING ===\n")

