#!/usr/bin/env Rscript

# Daily NSE Data Monitoring Script - Fixed Version
# This script monitors data freshness and runs incremental updates

# Load required libraries
library(dplyr)
library(lubridate)
library(httr)

# Set working directory
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')

# Source the data loading functions
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/getdataNSE.R')

# Function to check data status
check_data_status <- function() {
  cat("Checking data status...\n")
  
  # Check NSE stock data
  if(file.exists("nse_sec_full_data.csv")) {
    dt.nse <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
    dt.nse$TIMESTAMP <- as.Date(dt.nse$TIMESTAMP, format='%Y-%m-%d')
    nse_last_date <- max(dt.nse$TIMESTAMP, na.rm = TRUE)
    nse_records <- nrow(dt.nse)
  } else {
    nse_last_date <- NA
    nse_records <- 0
  }
  
  # Check NSE index data
  if(file.exists("nse_index_data.csv")) {
    dt.index <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
    dt.index$TIMESTAMP <- as.Date(dt.index$TIMESTAMP, format='%Y-%m-%d')
    index_last_date <- max(dt.index$TIMESTAMP, na.rm = TRUE)
    index_records <- nrow(dt.index)
  } else {
    index_last_date <- NA
    index_records <- 0
  }
  
  # Check audit files
  if(file.exists("audit.csv")) {
    audit <- read.csv("audit.csv", stringsAsFactors = FALSE)
    audit$last_load_dt <- as.Date(audit$last_load_dt, format='%Y-%m-%d')
    audit_last_date <- max(audit$last_load_dt, na.rm = TRUE)
  } else {
    audit_last_date <- NA
  }
  
  current_date <- Sys.Date()
  
  return(list(
    current_date = current_date,
    nse_last_date = nse_last_date,
    nse_records = nse_records,
    index_last_date = index_last_date,
    index_records = index_records,
    audit_last_date = audit_last_date
  ))
}

# Function to update data
update_data <- function() {
  cat("Starting data update...\n")
  
  tryCatch({
    # Update NSE stock data
    cat("Updating NSE stock data...\n")
    load_incr_nse_data(Sys.Date())
    
    # Update NSE index data
    cat("Updating NSE index data...\n")
    get_index_data(Sys.Date())
    
    cat("Data update completed successfully!\n")
    return(TRUE)
  }, error = function(e) {
    cat("Error during data update:", e$message, "\n")
    return(FALSE)
  })
}

# Function to print status report
print_status_report <- function(status_data) {
  cat("\n", paste(rep("=", 80), collapse = ""), "\n")
  cat("NSE DATA MONITORING STATUS REPORT\n")
  cat("Generated:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat(paste(rep("=", 80), collapse = ""), "\n\n")
  
  cat("Current Date:", as.character(status_data$current_date), "\n\n")
  
  cat("NSE Stock Data:\n")
  cat("  Last Date:", ifelse(is.na(status_data$nse_last_date), "No data", as.character(status_data$nse_last_date)), "\n")
  cat("  Total Records:", format(status_data$nse_records, big.mark = ","), "\n")
  cat("  Days Behind:", ifelse(is.na(status_data$nse_last_date), "Unknown", 
                              as.numeric(status_data$current_date - status_data$nse_last_date)), "\n\n")
  
  cat("NSE Index Data:\n")
  cat("  Last Date:", ifelse(is.na(status_data$index_last_date), "No data", as.character(status_data$index_last_date)), "\n")
  cat("  Total Records:", format(status_data$index_records, big.mark = ","), "\n")
  cat("  Days Behind:", ifelse(is.na(status_data$index_last_date), "Unknown", 
                              as.numeric(status_data$current_date - status_data$index_last_date)), "\n\n")
  
  cat("Audit File:\n")
  cat("  Last Update:", ifelse(is.na(status_data$audit_last_date), "No audit", as.character(status_data$audit_last_date)), "\n\n")
  
  # Determine if update is needed
  needs_update <- FALSE
  if(!is.na(status_data$nse_last_date)) {
    days_behind <- as.numeric(status_data$current_date - status_data$nse_last_date)
    if(days_behind > 1) {
      needs_update <- TRUE
      cat("⚠️  UPDATE NEEDED: NSE stock data is", days_behind, "days behind\n")
    }
  } else {
    needs_update <- TRUE
    cat("⚠️  UPDATE NEEDED: No NSE stock data found\n")
  }
  
  if(!needs_update) {
    cat("✅ Data is up to date\n")
  }
  
  cat("\n", paste(rep("-", 80), collapse = ""), "\n")
  cat("Summary:\n")
  cat("  Total NSE Records:", format(status_data$nse_records, big.mark = ","), "\n")
  cat("  Total Index Records:", format(status_data$index_records, big.mark = ","), "\n")
  cat("  Data Freshness:", ifelse(needs_update, "Needs Update", "Current"), "\n")
  cat(paste(rep("=", 80), collapse = ""), "\n\n")
  
  return(needs_update)
}

# Main execution
main <- function() {
  cat("Starting NSE Data Monitor...\n")
  cat("Time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n")
  
  # Check current status
  status_data <- check_data_status()
  
  # Print status report
  needs_update <- print_status_report(status_data)
  
  # Update if needed
  if(needs_update) {
    cat("Initiating data update...\n")
    update_success <- update_data()
    
    if(update_success) {
      cat("\n✅ Update completed successfully!\n")
      
      # Check status after update
      cat("\nChecking status after update...\n")
      new_status <- check_data_status()
      print_status_report(new_status)
    } else {
      cat("\n❌ Update failed!\n")
    }
  } else {
    cat("No update needed at this time.\n")
  }
  
  cat("\nMonitor completed at:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
}

# Run the main function
main()
