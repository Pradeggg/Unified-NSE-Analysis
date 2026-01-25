# Test script for overallperformance function
# This script tests the overallperformance function with proper error handling

# Load required libraries
suppressPackageStartupMessages({
  library(stringr)
  library(dplyr)
  library(rvest)
  library(tidyr)
})

# Source the screenerdata.R file
cat("Loading screenerdata.R functions...\n")

# Test a simple stock data extraction first
test_simple_function <- function() {
  tryCatch({
    # Test quarterly results function
    cat("Testing get_screener_quarterly_results_data function...\n")
    quarterly_data <- get_screener_quarterly_results_data('RELIANCE')
    cat("✅ Quarterly data retrieved successfully\n")
    return(TRUE)
  }, error = function(e) {
    cat("❌ Error in quarterly data function:", e$message, "\n")
    return(FALSE)
  })
}

# Test overallperformance with error handling
test_overallperformance <- function(symbol) {
  cat("Testing overallperformance function for", symbol, "...\n")
  
  result <- tryCatch({
    score <- overallperformance(symbol)
    list(success = TRUE, score = as.numeric(score), error = NULL)
  }, error = function(e) {
    list(success = FALSE, score = NA, error = e$message)
  })
  
  if (result$success) {
    cat("✅", symbol, "Overall Performance Score:", round(result$score, 2), "\n")
  } else {
    cat("❌", symbol, "Error:", result$error, "\n")
  }
  
  return(result)
}

# Test superperformance function individually
test_superperformance <- function(symbol, category) {
  cat("Testing superperformance function for", symbol, "category:", category, "...\n")
  
  result <- tryCatch({
    data <- superperformance(symbol, category)
    list(success = TRUE, data = data, error = NULL)
  }, error = function(e) {
    list(success = FALSE, data = NULL, error = e$message)
  })
  
  if (result$success) {
    cat("✅", symbol, category, "analysis completed successfully\n")
    if (is.data.frame(result$data) && nrow(result$data) > 0) {
      print(head(result$data, 3))
    }
  } else {
    cat("❌", symbol, category, "Error:", result$error, "\n")
  }
  
  return(result)
}

cat("Starting comprehensive tests...\n")
cat(paste(rep("=", 50), collapse=""), "\n")
