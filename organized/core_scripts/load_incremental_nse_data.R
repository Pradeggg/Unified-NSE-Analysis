#!/usr/bin/env Rscript

# =============================================================================
# Load Incremental NSE Data Script
# =============================================================================
# This script loads incremental NSE data for specific dates using the 
# load_incr_nse_data function from getdataNSE.R
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
load_incremental_data_for_dates <- function(target_dates) {
  cat("=== LOADING INCREMENTAL NSE DATA ===\n")
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
      load_incr_nse_data(target_date)
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
    recent_dates <- sort(unique(final_data$TIMESTAMP), decreasing = TRUE)[1:5]
    cat("Latest 5 dates:", paste(as.character(recent_dates), collapse = ", "), "\n")
  }
}

# Function to load data for a date range
load_incremental_data_for_range <- function(start_date, end_date) {
  cat("=== LOADING INCREMENTAL DATA FOR DATE RANGE ===\n")
  cat("Start date:", as.character(start_date), "\n")
  cat("End date:", as.character(end_date), "\n\n")
  
  # Generate sequence of dates and filter for trading days only
  all_dates <- seq(start_date, end_date, by = "day")
  trading_dates <- all_dates[lubridate::wday(all_dates) %in% 2:6]  # Monday = 2, Friday = 6
  
  cat("Trading days to process:", length(trading_dates), "\n")
  cat("Dates:", paste(as.character(trading_dates), collapse = ", "), "\n\n")
  
  # Load data for each trading day
  load_incremental_data_for_dates(trading_dates)
}

# Function to load data for the last N days
load_incremental_data_for_last_n_days <- function(n_days = 5) {
  cat("=== LOADING INCREMENTAL DATA FOR LAST", n_days, "DAYS ===\n")
  
  # Calculate date range
  end_date <- Sys.Date() - 1  # Yesterday
  start_date <- end_date - (n_days - 1)
  
  cat("Date range:", as.character(start_date), "to", as.character(end_date), "\n\n")
  
  load_incremental_data_for_range(start_date, end_date)
}

# Main execution
cat("=== INCREMENTAL NSE DATA LOADER ===\n")
cat("Date:", format(Sys.Date(), "%B %d, %Y"), "\n\n")

# Check command line arguments
args <- commandArgs(trailingOnly = TRUE)

if(length(args) > 0) {
  if(args[1] == "last" && length(args) > 1) {
    # Load data for last N days
    n_days <- as.numeric(args[2])
    if(!is.na(n_days) && n_days > 0) {
      load_incremental_data_for_last_n_days(n_days)
    } else {
      cat("Invalid number of days. Using default: 5\n")
      load_incremental_data_for_last_n_days(5)
    }
  } else if(args[1] == "range" && length(args) > 2) {
    # Load data for date range
    start_date <- as.Date(args[2])
    end_date <- as.Date(args[3])
    if(!is.na(start_date) && !is.na(end_date)) {
      load_incremental_data_for_range(start_date, end_date)
    } else {
      cat("Invalid date format. Use YYYY-MM-DD\n")
    }
  } else if(args[1] == "dates" && length(args) > 1) {
    # Load data for specific dates
    target_dates <- as.Date(args[-1])
    if(all(!is.na(target_dates))) {
      load_incremental_data_for_dates(target_dates)
    } else {
      cat("Invalid date format. Use YYYY-MM-DD\n")
    }
  } else {
    cat("Invalid arguments. Usage:\n")
    cat("  Rscript load_incremental_nse_data.R last <n_days>\n")
    cat("  Rscript load_incremental_nse_data.R range <start_date> <end_date>\n")
    cat("  Rscript load_incremental_nse_data.R dates <date1> <date2> ...\n")
    cat("  Rscript load_incremental_nse_data.R\n")
  }
} else {
  # Default: Load data for September 11 and 12, 2025 (the missing dates we identified)
  cat("No arguments provided. Loading data for September 11 and 12, 2025...\n\n")
  target_dates <- c(as.Date("2025-09-11"), as.Date("2025-09-12"))
  load_incremental_data_for_dates(target_dates)
}

cat("\n=== SCRIPT COMPLETED ===\n")


