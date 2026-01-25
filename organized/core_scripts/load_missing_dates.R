#!/usr/bin/env Rscript

# =============================================================================
# Load Missing NSE Data for September 15-19, 2025
# =============================================================================
# This script loads missing NSE data for specific dates
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(lubridate)
  library(httr)
})

# Set working directory to NSE data location
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')

# Source the getdataNSE.R file to get access to the functions
cat("Loading getdataNSE.R functions...\n")
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/getdataNSE.R')

# Function to load incremental data for specific dates
load_missing_dates <- function(target_dates) {
  cat("=== LOADING MISSING NSE DATA ===\n")
  cat("Target dates:", paste(target_dates, collapse = ", "), "\n\n")
  
  # Check current data status
  if(file.exists("nse_sec_full_data.csv")) {
    current_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
    current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
    
    latest_date <- max(current_data$TIMESTAMP, na.rm = TRUE)
    total_records <- nrow(current_data)
    
    cat("Current data status:\n")
    cat("- Latest date:", as.character(latest_date), "\n")
    cat("- Total records:", total_records, "\n")
    cat("- Date range:", as.character(min(current_data$TIMESTAMP, na.rm = TRUE)), "to", as.character(latest_date), "\n\n")
  } else {
    cat("⚠️ nse_sec_full_data.csv not found. Will create new file.\n\n")
  }
  
  # Process each target date
  for(target_date in target_dates) {
    cat("=== Processing", as.character(target_date), "===\n")
    
    # Check if data already exists for this date
    if(file.exists("nse_sec_full_data.csv")) {
      current_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
      current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
      
      existing_records <- sum(current_data$TIMESTAMP == target_date, na.rm = TRUE)
      if(existing_records > 0) {
        cat("✓ Data already exists for", as.character(target_date), ":", existing_records, "records\n")
        next
      }
    }
    
    # Load incremental data for this date
    tryCatch({
      # Convert date to proper format for the function
      date_str <- as.character(target_date)
      cat("Loading data for date:", date_str, "\n")
      
      # Call the load_incr_nse_data function with the date string
      load_incr_nse_data(date_str)
      cat("✓ Successfully processed", as.character(target_date), "\n")
    }, error = function(e) {
      cat("✗ Error processing", as.character(target_date), ":", e$message, "\n")
    })
    
    cat("\n")
  }
  
  # Final status check
  if(file.exists("nse_sec_full_data.csv")) {
    final_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
    final_data$TIMESTAMP <- as.Date(final_data$TIMESTAMP)
    
    final_latest_date <- max(final_data$TIMESTAMP, na.rm = TRUE)
    final_total_records <- nrow(final_data)
    
    cat("=== FINAL STATUS ===\n")
    cat("Latest date:", as.character(final_latest_date), "\n")
    cat("Total records:", final_total_records, "\n")
    
    # Check for the target dates
    for(target_date in target_dates) {
      records_for_date <- sum(final_data$TIMESTAMP == target_date, na.rm = TRUE)
      cat("Records for", as.character(target_date), ":", records_for_date, "\n")
    }
    
    # Show recent dates
    recent_dates <- sort(unique(final_data$TIMESTAMP), decreasing = TRUE)[1:10]
    cat("Latest 10 dates:", paste(as.character(recent_dates), collapse = ", "), "\n")
  }
}

# Main execution
cat("=== LOADING MISSING NSE DATA FOR SEPTEMBER 15-19, 2025 ===\n")
cat("Date:", format(Sys.Date(), "%B %d, %Y"), "\n\n")

# Define the missing dates (September 15-19, 2025)
missing_dates <- c(
  as.Date("2025-09-15"),  # Monday
  as.Date("2025-09-16"),  # Tuesday
  as.Date("2025-09-17"),  # Wednesday
  as.Date("2025-09-18"),  # Thursday
  as.Date("2025-09-19")   # Friday
)

# Load the missing dates
load_missing_dates(missing_dates)

cat("\n=== SCRIPT COMPLETED ===\n")
