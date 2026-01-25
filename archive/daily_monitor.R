#!/usr/bin/env Rscript

# ================================================================================
# DAILY NSE DATA MONITORING SCRIPT
# ================================================================================
# This script monitors and updates NSE data on a daily basis
# Author: System Administrator
# Date: 2025-08-31
# ================================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(lubridate)
  library(httr)
  library(readr)
})

# Set working directory to NSE-index folder
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')

# Source the data loading functions
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/getdataNSE.R')

# ================================================================================
# MONITORING FUNCTIONS
# ================================================================================

#' Check data freshness for a given CSV file
#' @param file_path Path to the CSV file
#' @param date_column Name of the date column
#' @return List with freshness status and details
check_data_freshness <- function(file_path, date_column = "TIMESTAMP") {
  if (!file.exists(file_path)) {
    return(list(
      status = "MISSING",
      message = paste("File not found:", file_path),
      last_date = NULL,
      days_behind = NULL
    ))
  }
  
  tryCatch({
    # Read the data
    data <- read.csv(file_path, stringsAsFactors = FALSE)
    
    if (nrow(data) == 0) {
      return(list(
        status = "EMPTY",
        message = paste("File is empty:", file_path),
        last_date = NULL,
        days_behind = NULL
      ))
    }
    
    # Convert date column
    data[[date_column]] <- as.Date(data[[date_column]], format = "%Y-%m-%d")
    last_date <- max(data[[date_column]], na.rm = TRUE)
    current_date <- Sys.Date()
    days_behind <- as.numeric(current_date - last_date)
    
    # Determine status
    if (days_behind <= 1) {
      status <- "FRESH"
      message <- paste("Data is up to date. Last update:", last_date)
    } else if (days_behind <= 3) {
      status <- "STALE"
      message <- paste("Data is", days_behind, "days old. Last update:", last_date)
    } else {
      status <- "OUTDATED"
      message <- paste("Data is", days_behind, "days old. Needs immediate update. Last update:", last_date)
    }
    
    return(list(
      status = status,
      message = message,
      last_date = last_date,
      days_behind = days_behind
    ))
    
  }, error = function(e) {
    return(list(
      status = "ERROR",
      message = paste("Error reading file:", e$message),
      last_date = NULL,
      days_behind = NULL
    ))
  })
}

#' Run incremental data updates
#' @param target_date Target date for updates (default: yesterday)
#' @return List with update results
run_incremental_updates <- function(target_date = Sys.Date() - 1) {
  cat("Starting incremental data updates for", as.character(target_date), "\n")
  
  results <- list()
  
  # Update NSE stock data
  cat("Updating NSE stock data...\n")
  tryCatch({
    load_incr_nse_data(target_date)
    results$nse_stock <- "SUCCESS"
    cat("✓ NSE stock data updated successfully\n")
  }, error = function(e) {
    results$nse_stock <- paste("FAILED:", e$message)
    cat("✗ NSE stock data update failed:", e$message, "\n")
  })
  
  # Update BSE stock data
  cat("Updating BSE stock data...\n")
  tryCatch({
    load_incr_bse_data(target_date)
    results$bse_stock <- "SUCCESS"
    cat("✓ BSE stock data updated successfully\n")
  }, error = function(e) {
    results$bse_stock <- paste("FAILED:", e$message)
    cat("✗ BSE stock data update failed:", e$message, "\n")
  })
  
  # Update index data
  cat("Updating index data...\n")
  tryCatch({
    get_index_data(Sys.Date())
    results$index_data <- "SUCCESS"
    cat("✓ Index data updated successfully\n")
  }, error = function(e) {
    results$index_data <- paste("FAILED:", e$message)
    cat("✗ Index data update failed:", e$message, "\n")
  })
  
  return(results)
}

#' Generate comprehensive status report
#' @return Data frame with status information
generate_status_report <- function() {
  cat("Generating comprehensive status report...\n")
  
  # Files to monitor
  files_to_monitor <- list(
    list(file = "nse_sec_full_data.csv", name = "NSE Stock Data", date_col = "TIMESTAMP"),
    list(file = "bse_sec_full_data.csv", name = "BSE Stock Data", date_col = "TIMESTAMP"),
    list(file = "nse_index_data.csv", name = "NSE Index Data", date_col = "TIMESTAMP"),
    list(file = "nse_mto_data.csv", name = "NSE MTO Data", date_col = "Date"),
    list(file = "nse_circuit_breakers_data.csv", name = "NSE Circuit Breakers", date_col = "date")
  )
  
  status_data <- data.frame()
  
  for (file_info in files_to_monitor) {
    freshness <- check_data_freshness(file_info$file, file_info$date_col)
    
    status_data <- rbind(status_data, data.frame(
      File = file_info$name,
      Status = freshness$status,
      Last_Update = as.character(freshness$last_date),
      Days_Behind = freshness$days_behind,
      Message = freshness$message,
      stringsAsFactors = FALSE
    ))
  }
  
  return(status_data)
}

#' Print formatted status report
#' @param status_data Status data frame
print_status_report <- function(status_data) {
  cat("\n", paste(rep("=", 80), collapse = ""), "\n")
  cat("NSE DATA MONITORING STATUS REPORT\n")
  cat("Generated:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat(paste(rep("=", 80), collapse = ""), "\n\n")
  
  for (i in 1:nrow(status_data)) {
    row <- status_data[i, ]
    
    # Color coding for status
    status_icon <- switch(row$Status,
      "FRESH" = "✓",
      "STALE" = "⚠",
      "OUTDATED" = "✗",
      "MISSING" = "❌",
      "ERROR" = "💥",
      "EMPTY" = "📭"
    )
    
    cat(sprintf("%s %-25s | %-10s | %-12s | %-3s days | %s\n",
                status_icon,
                row$File,
                row$Status,
                ifelse(is.na(row$Last_Update), "N/A", row$Last_Update),
                ifelse(is.na(row$Days_Behind), "N/A", row$Days_Behind),
                row$Message
    ))
  }
  
  cat("\n", paste(rep("-", 80), collapse = ""), "\n")
  
  # Summary statistics
  total_files <- nrow(status_data)
  fresh_files <- sum(status_data$Status == "FRESH", na.rm = TRUE)
  stale_files <- sum(status_data$Status == "STALE", na.rm = TRUE)
  outdated_files <- sum(status_data$Status == "OUTDATED", na.rm = TRUE)
  error_files <- sum(status_data$Status %in% c("MISSING", "ERROR", "EMPTY"), na.rm = TRUE)
  
  cat(sprintf("SUMMARY: %d total files | %d fresh | %d stale | %d outdated | %d errors\n",
              total_files, fresh_files, stale_files, outdated_files, error_files))
  
  cat(paste(rep("=", 80), collapse = ""), "\n\n")
}

# ================================================================================
# MAIN EXECUTION
# ================================================================================

main <- function() {
  cat("Starting NSE Data Daily Monitor...\n")
  cat("Time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n")
  
  # Step 1: Generate current status report
  cat("Step 1: Checking current data status...\n")
  status_report <- generate_status_report()
  print_status_report(status_report)
  
  # Step 2: Determine if updates are needed
  needs_update <- any(status_report$Status %in% c("OUTDATED", "STALE"), na.rm = TRUE)
  
  if (needs_update) {
    cat("Step 2: Updates needed. Running incremental updates...\n")
    update_results <- run_incremental_updates()
    
    cat("\nStep 3: Generating updated status report...\n")
    updated_status <- generate_status_report()
    print_status_report(updated_status)
    
    # Step 4: Save monitoring log
    log_entry <- data.frame(
      timestamp = Sys.time(),
      action = "daily_monitor",
      files_updated = sum(update_results == "SUCCESS"),
      total_files = length(update_results),
      status = ifelse(all(update_results == "SUCCESS"), "SUCCESS", "PARTIAL"),
      details = paste(names(update_results), update_results, collapse = "; ")
    )
    
    # Append to monitoring log
    if (file.exists("monitoring_log.csv")) {
      write.table(log_entry, "monitoring_log.csv", append = TRUE, 
                  row.names = FALSE, col.names = FALSE, sep = ",")
    } else {
      write.csv(log_entry, "monitoring_log.csv", row.names = FALSE)
    }
    
    cat("✓ Monitoring log updated\n")
    
  } else {
    cat("Step 2: No updates needed. All data is fresh.\n")
  }
  
  cat("\nDaily monitoring completed successfully!\n")
  cat("Time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
}

# Run the main function
if (!interactive()) {
  main()
} else {
  cat("Running in interactive mode. Call main() to execute monitoring.\n")
}
