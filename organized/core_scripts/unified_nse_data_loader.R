#!/usr/bin/env Rscript

# =============================================================================
# Unified NSE Data Loader
# =============================================================================
# This script provides comprehensive NSE data loading functionality including:
# - Stock data loading with proper error handling
# - Index data loading with correct PR file approach
# - Data validation and quality checks
# - Data caching for the project
# - Command-line argument support for flexibility
# - Fallback mechanisms for robust data loading
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(lubridate)
  library(httr)
  library(jsonlite)
})

# =============================================================================
# Configuration and Setup
# =============================================================================

# Set working directory to NSE data location
nse_data_path <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index"
project_data_dir <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data"

# Create directories if they don't exist
if (!dir.exists(project_data_dir)) {
  dir.create(project_data_dir, recursive = TRUE)
}

# Set working directory
setwd(nse_data_path)

# Load the getdataNSE.R file to get data loading functions
cat("Loading NSE data loading functions...\n")
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/getdataNSE.R')

# =============================================================================
# Utility Functions
# =============================================================================

# Function to check if a date is a trading day (Monday to Friday)
is_trading_day <- function(date) {
  wday(date) %in% 2:6  # Monday = 2, Friday = 6
}

# Function to get the last trading day
get_last_trading_day <- function() {
  today <- Sys.Date()
  # Go back up to 7 days to find the last trading day
  for (i in 0:6) {
    check_date <- today - i
    if (is_trading_day(check_date)) {
      return(check_date)
    }
  }
  return(today - 7)  # Fallback
}

# Function to validate data quality
validate_data_quality <- function(data, data_type = "stock") {
  cat("Validating", data_type, "data quality...\n")
  
  if (nrow(data) == 0) {
    cat("❌ No data found\n")
    return(FALSE)
  }
  
  # Check for required columns
  required_cols <- if (data_type == "stock") {
    c("SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE")
  } else {
    c("SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE")
  }
  
  missing_cols <- setdiff(required_cols, names(data))
  if (length(missing_cols) > 0) {
    cat("❌ Missing required columns:", paste(missing_cols, collapse = ", "), "\n")
    return(FALSE)
  }
  
  # Check for missing values in critical columns
  critical_cols <- c("SYMBOL", "TIMESTAMP", "CLOSE")
  for (col in critical_cols) {
    missing_count <- sum(is.na(data[[col]]) | data[[col]] == "")
    if (missing_count > 0) {
      cat("⚠️ Missing values in", col, ":", missing_count, "records\n")
    }
  }
  
  # Check for duplicate records
  if (data_type == "stock") {
    duplicates <- data %>% 
      group_by(SYMBOL, TIMESTAMP) %>% 
      summarise(count = n(), .groups = "drop") %>% 
      filter(count > 1)
    
    if (nrow(duplicates) > 0) {
      cat("⚠️ Duplicate records found:", nrow(duplicates), "symbol-date combinations\n")
    }
  }
  
  cat("✅ Data validation completed\n")
  return(TRUE)
}

# =============================================================================
# Stock Data Loading Functions
# =============================================================================

# Function to load stock data for a specific date
load_stock_data_for_date <- function(target_date) {
  cat("Loading stock data for", as.character(target_date), "...\n")
  
  tryCatch({
    # Convert date to proper string format
    date_str <- format(target_date, "%Y-%m-%d")
    
    # Use the working NSE URL pattern: PR folder with capital PR + DDMMYY format
    urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                    toupper(format(target_date, "%d%m%y")), ".zip", sep = "")
    tempzip <- paste0("PR", toupper(format(target_date, "%d%m%y")), ".zip", sep = "")
    tempfilename <- paste("Pd", toupper(format(target_date, "%d%m%y")), ".csv", sep = "")
    
    cat("Downloading from:", urllink, "\n")
    
    # Download using GET with User-Agent header
    response <- httr::GET(urllink, 
                         httr::write_disk(tempzip, overwrite = TRUE),
                         httr::add_headers(`User-Agent` = "Mozilla/5.0"))
    
    if (response$status_code == 200) {
      # Extract the Pd*.csv file
      unzip(tempzip, tempfilename, overwrite = TRUE)
      
      if (file.exists(tempfilename)) {
        # Read the data
        raw_data <- read.csv(tempfilename, stringsAsFactors = FALSE)
        
        # Filter for equity stocks only
        stock_data <- raw_data %>% 
          filter(SERIES == "EQ" & !is.na(SYMBOL) & SYMBOL != " " & SYMBOL != "")
        
        if (nrow(stock_data) > 0) {
          # Map the Pd*.csv columns to standard format
          processed_data <- stock_data %>%
            mutate(
              SYMBOL = SYMBOL,
              SERIES = SERIES,
              OPEN = as.numeric(OPEN_PRICE),
              HIGH = as.numeric(HIGH_PRICE),
              LOW = as.numeric(LOW_PRICE),
              CLOSE = as.numeric(CLOSE_PRICE),
              LAST = as.numeric(CLOSE_PRICE),
              PREVCLOSE = as.numeric(PREV_CL_PR),
              TOTTRDQTY = as.numeric(NET_TRDQTY),
              TOTTRDVAL = as.numeric(NET_TRDVAL),
              TIMESTAMP = format(target_date, "%Y-%m-%d"),
              TOTALTRADES = as.numeric(TRADES),
              ISIN = NA
            ) %>%
            select(SYMBOL, ISIN, TIMESTAMP, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, 
                   TOTTRDQTY, TOTTRDVAL, TOTALTRADES) %>%
            filter(!is.na(CLOSE) & !is.na(OPEN) & !is.na(HIGH) & !is.na(LOW))
          
          # Clean up temporary files
          if (file.exists(tempfilename)) file.remove(tempfilename)
          if (file.exists(tempzip)) file.remove(tempzip)
          
          cat("✅ Successfully loaded", nrow(processed_data), "stock records for", as.character(target_date), "\n")
          return(processed_data)
        } else {
          cat("❌ No equity data found for", as.character(target_date), "\n")
          return(NULL)
        }
      } else {
        cat("❌ Could not extract data file for", as.character(target_date), "\n")
        return(NULL)
      }
    } else {
      cat("❌ Download failed for", as.character(target_date), "- Status code:", response$status_code, "\n")
      return(NULL)
    }
  }, error = function(e) {
    cat("❌ Error loading stock data for", as.character(target_date), ":", e$message, "\n")
    return(NULL)
  })
}

# Function to load stock data for specific dates
load_stock_data_for_dates <- function(target_dates) {
  cat("=== LOADING STOCK DATA ===\n")
  cat("Target dates:", paste(target_dates, collapse = ", "), "\n\n")
  
  # Check current data status
  if(file.exists("nse_sec_full_data.csv")) {
    current_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
    current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
    
    latest_date <- max(current_data$TIMESTAMP, na.rm = TRUE)
    total_records <- nrow(current_data)
    
    cat("Current stock data status:\n")
    cat("- Latest date:", as.character(latest_date), "\n")
    cat("- Total records:", total_records, "\n")
    cat("- Date range:", as.character(min(current_data$TIMESTAMP, na.rm = TRUE)), "to", as.character(latest_date), "\n\n")
  } else {
    cat("⚠️ nse_sec_full_data.csv not found. Will create new file.\n\n")
  }
  
  # Process each target date
  for(i in 1:length(target_dates)) {
    target_date <- target_dates[i]
    cat("=== Processing Stock Data for", as.character(target_date), "===\n")
    
    # Check if data already exists for this date
    if(file.exists("nse_sec_full_data.csv")) {
      current_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
      current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
      
      existing_records <- sum(current_data$TIMESTAMP == target_date, na.rm = TRUE)
      if(existing_records > 0) {
        cat("✓ Stock data already exists for", as.character(target_date), ":", existing_records, "records\n")
        next
      }
    }
    
    # Load stock data for this date
    new_data <- load_stock_data_for_date(target_date)
    
    if (!is.null(new_data)) {
      # Read existing data and append
      if (file.exists("nse_sec_full_data.csv")) {
        existing_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
        combined_data <- rbind(existing_data, new_data)
        # Remove duplicates
        combined_data <- combined_data %>%
          distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
      } else {
        combined_data <- new_data
      }
      
      # Write back to file
      write.csv(combined_data, "nse_sec_full_data.csv", row.names = FALSE)
      cat("✅ Stock data updated successfully for", as.character(target_date), "\n")
    } else {
      cat("❌ Failed to load stock data for", as.character(target_date), "\n")
    }
    
    cat("\n")
  }
}

# =============================================================================
# Index Data Loading Functions
# =============================================================================

# Function to load index data for a specific date
load_index_data_for_date <- function(target_date) {
  cat("Loading index data for", as.character(target_date), "...\n")
  
  tryCatch({
    # Convert date to proper string format
    date_str <- format(target_date, "%Y-%m-%d")
    
    # Use the same PR file approach as stock data but filter for index data
    tdata <- as.Date(date_str, format = "%Y-%m-%d")
    
    # Use the working NSE URL pattern: PR folder with capital PR + DDMMYY format
    urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                    toupper(format(tdata, "%d%m%y")), ".zip", sep = "")
    tempzip <- paste0("PR", toupper(format(tdata, "%d%m%y")), ".zip", sep = "")
    tempfilename <- paste("Pr", toupper(format(tdata, "%d%m%y")), ".csv", sep = "")
    
    cat("Downloading index data from:", urllink, "\n")
    
    # Download using GET with User-Agent header
    response <- httr::GET(urllink, 
                         httr::write_disk(tempzip, overwrite = TRUE),
                         httr::add_headers(`User-Agent` = "Mozilla/5.0"))
    
    if (response$status_code == 200) {
      # Extract the Pr*.csv file (index data file)
      unzip(tempzip, tempfilename, overwrite = TRUE)
      
      if (file.exists(tempfilename)) {
        # Read the data
        raw_data <- read.csv(tempfilename, stringsAsFactors = FALSE)
        
        # Filter for index data only (IND_SEC=="Y" & MKT == "Y")
        index_data <- raw_data %>% 
          filter(IND_SEC == "Y" & MKT == "Y" & !is.na(SECURITY) & SECURITY != " " & SECURITY != "")
        
        if (nrow(index_data) > 0) {
          # Rename columns to match the actual Pr*.csv structure
          colnames(index_data) <- c("MKT", "SECURITY", "PREVCLOSE", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDVAL",
                                  "TOTTRDQTY", "IND_SEC", "CORP_IND", "TOTALTRADES", "HI_52_WK", "LO_52_WK")
          
          # Map the renamed columns to standard format for index data
          processed_data <- index_data %>%
            mutate(
              SYMBOL = SECURITY,
              OPEN = as.numeric(OPEN),
              HIGH = as.numeric(HIGH),
              LOW = as.numeric(LOW),
              CLOSE = as.numeric(CLOSE),
              PREVCLOSE = as.numeric(PREVCLOSE),
              TOTTRDQTY = as.numeric(TOTTRDQTY),
              TOTTRDVAL = as.numeric(TOTTRDVAL),
              TIMESTAMP = format(target_date, "%Y-%m-%d"),
              TOTALTRADES = as.numeric(TOTALTRADES),
              HI_52_WK = as.numeric(HI_52_WK),
              LO_52_WK = as.numeric(LO_52_WK)
            ) %>%
            select(SYMBOL, OPEN, HIGH, LOW, CLOSE, PREVCLOSE, 
                   TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, HI_52_WK, LO_52_WK) %>%
            filter(!is.na(CLOSE) & !is.na(OPEN) & !is.na(HIGH) & !is.na(LOW))
          
          # Clean up temporary files
          if (file.exists(tempfilename)) file.remove(tempfilename)
          if (file.exists(tempzip)) file.remove(tempzip)
          
          cat("✅ Successfully loaded", nrow(processed_data), "index records for", as.character(target_date), "\n")
          return(processed_data)
        } else {
          cat("❌ No index data found for", as.character(target_date), "\n")
          return(NULL)
        }
      } else {
        cat("❌ Could not extract index data file for", as.character(target_date), "\n")
        return(NULL)
      }
    } else {
      cat("❌ Download failed for index data on", as.character(target_date), "- Status code:", response$status_code, "\n")
      return(NULL)
    }
  }, error = function(e) {
    cat("❌ Error loading index data for", as.character(target_date), ":", e$message, "\n")
    return(NULL)
  })
}

# Function to load index data for specific dates
load_index_data_for_dates <- function(target_dates) {
  cat("=== LOADING INDEX DATA ===\n")
  cat("Target dates:", paste(target_dates, collapse = ", "), "\n\n")
  
  # Check current index data status
  if(file.exists("nse_index_data.csv")) {
    current_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
    current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
    
    latest_date <- max(current_data$TIMESTAMP, na.rm = TRUE)
    total_records <- nrow(current_data)
    
    cat("Current index data status:\n")
    cat("- Latest date:", as.character(latest_date), "\n")
    cat("- Total records:", total_records, "\n")
    cat("- Date range:", as.character(min(current_data$TIMESTAMP, na.rm = TRUE)), "to", as.character(latest_date), "\n\n")
  } else {
    cat("⚠️ nse_index_data.csv not found. Will create new file.\n\n")
  }
  
  # Process each target date
  for(i in 1:length(target_dates)) {
    target_date <- target_dates[i]
    cat("=== Processing Index Data for", as.character(target_date), "===\n")
    
    # Check if data already exists for this date
    if(file.exists("nse_index_data.csv")) {
      current_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
      current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
      
      existing_records <- sum(current_data$TIMESTAMP == target_date, na.rm = TRUE)
      if(existing_records > 0) {
        cat("✓ Index data already exists for", as.character(target_date), ":", existing_records, "records\n")
        next
      }
    }
    
    # Load index data for this date
    new_data <- load_index_data_for_date(target_date)
    
    if (!is.null(new_data)) {
      # Read existing data and append
      if (file.exists("nse_index_data.csv")) {
        existing_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
        combined_data <- rbind(existing_data, new_data)
        # Remove duplicates
        combined_data <- combined_data %>%
          distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
      } else {
        combined_data <- new_data
      }
      
      # Write back to file
      write.csv(combined_data, "nse_index_data.csv", row.names = FALSE)
      cat("✅ Index data updated successfully for", as.character(target_date), "\n")
    } else {
      cat("❌ Failed to load index data for", as.character(target_date), "\n")
    }
    
    cat("\n")
  }
}

# =============================================================================
# Data Caching and Project Integration
# =============================================================================

# Function to cache data for the project
cache_data_for_project <- function() {
  cat("=== CACHING DATA FOR PROJECT ===\n")
  
  # Load the updated data
  if(file.exists("nse_sec_full_data.csv")) {
    stock_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
    stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)
    
    # Save stock data
    save(stock_data, file = file.path(project_data_dir, "nse_stock_cache.RData"))
    cat("✅ Stock data cached to:", file.path(project_data_dir, "nse_stock_cache.RData"), "\n")
  } else {
    cat("❌ Stock data file not found\n")
    stock_data <- NULL
  }
  
  if(file.exists("nse_index_data.csv")) {
    index_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
    index_data$TIMESTAMP <- as.Date(index_data$TIMESTAMP)
    
    # Save index data
    save(index_data, file = file.path(project_data_dir, "nse_index_cache.RData"))
    cat("✅ Index data cached to:", file.path(project_data_dir, "nse_index_cache.RData"), "\n")
  } else {
    cat("❌ Index data file not found\n")
    index_data <- NULL
  }
  
  # Create a summary file
  summary_data <- list(
    timestamp = Sys.time(),
    stock_records = if (!is.null(stock_data)) nrow(stock_data) else 0,
    index_records = if (!is.null(index_data)) nrow(index_data) else 0,
    stock_date_range = if (!is.null(stock_data)) {
      c(as.character(min(stock_data$TIMESTAMP)), as.character(max(stock_data$TIMESTAMP)))
    } else c(NA, NA),
    index_date_range = if (!is.null(index_data)) {
      c(as.character(min(index_data$TIMESTAMP)), as.character(max(index_data$TIMESTAMP)))
    } else c(NA, NA),
    unique_stocks = if (!is.null(stock_data)) length(unique(stock_data$SYMBOL)) else 0,
    unique_indices = if (!is.null(index_data)) length(unique(index_data$SYMBOL)) else 0
  )
  
  write_json(summary_data, file.path(project_data_dir, "data_summary.json"), pretty = TRUE)
  cat("✅ Data summary saved to:", file.path(project_data_dir, "data_summary.json"), "\n")
  
  return(list(stock_data = stock_data, index_data = index_data))
}

# =============================================================================
# Main Execution
# =============================================================================

# Main execution
cat("=== UNIFIED NSE DATA LOADER ===\n")
cat("Date:", format(Sys.Date(), "%B %d, %Y"), "\n")
cat("NSE Data Path:", nse_data_path, "\n")
cat("Project Data Path:", project_data_dir, "\n\n")

# Check command line arguments for flexibility
args <- commandArgs(trailingOnly = TRUE)

if(length(args) > 0) {
  if(args[1] == "last" && length(args) > 1) {
    # Load data for last N days
    n_days <- as.numeric(args[2])
    if(!is.na(n_days) && n_days > 0) {
      end_date <- Sys.Date() - 1
      start_date <- end_date - (n_days - 1)
      target_dates <- seq(start_date, end_date, by = "day")
      target_dates <- target_dates[lubridate::wday(target_dates) %in% 2:6]  # Trading days only
      cat("Loading data for last", n_days, "trading days...\n")
    } else {
      cat("Invalid number of days. Loading latest data...\n")
      target_dates <- c(get_last_trading_day())
    }
  } else if(args[1] == "range" && length(args) > 2) {
    # Load data for date range
    start_date <- as.Date(args[2])
    end_date <- as.Date(args[3])
    if(!is.na(start_date) && !is.na(end_date)) {
      target_dates <- seq(start_date, end_date, by = "day")
      target_dates <- target_dates[lubridate::wday(target_dates) %in% 2:6]  # Trading days only
      cat("Loading data for date range:", as.character(start_date), "to", as.character(end_date), "\n")
    } else {
      cat("Invalid date format. Loading latest data...\n")
      target_dates <- c(get_last_trading_day())
    }
  } else if(args[1] == "dates" && length(args) > 1) {
    # Load data for specific dates
    target_dates <- as.Date(args[-1])
    if(all(!is.na(target_dates))) {
      cat("Loading data for specific dates:", paste(as.character(target_dates), collapse = ", "), "\n")
    } else {
      cat("Invalid date format. Loading latest data...\n")
      target_dates <- c(get_last_trading_day())
    }
  } else {
    cat("Invalid arguments. Usage:\n")
    cat("  Rscript unified_nse_data_loader.R last <n_days>\n")
    cat("  Rscript unified_nse_data_loader.R range <start_date> <end_date>\n")
    cat("  Rscript unified_nse_data_loader.R dates <date1> <date2> ...\n")
    cat("  Rscript unified_nse_data_loader.R\n")
    cat("Loading latest data...\n")
    target_dates <- c(get_last_trading_day())
  }
} else {
  # Default: Load latest data
  cat("No arguments provided. Loading latest data...\n")
  target_dates <- c(get_last_trading_day())
}

# Load stock data for specified dates
load_stock_data_for_dates(target_dates)

# Load index data for specified dates
load_index_data_for_dates(target_dates)

# Cache data for the project
cached_data <- cache_data_for_project()

# =============================================================================
# Final Summary
# =============================================================================

cat("\n=== FINAL DATA LOADING SUMMARY ===\n")

if (!is.null(cached_data$stock_data)) {
  cat("Stock Data:\n")
  cat("- Records:", nrow(cached_data$stock_data), "\n")
  cat("- Date range:", as.character(min(cached_data$stock_data$TIMESTAMP)), "to", as.character(max(cached_data$stock_data$TIMESTAMP)), "\n")
  cat("- Unique stocks:", length(unique(cached_data$stock_data$SYMBOL)), "\n")
  cat("- Latest date:", as.character(max(cached_data$stock_data$TIMESTAMP)), "\n")
} else {
  cat("Stock Data: ❌ Failed to load\n")
}

if (!is.null(cached_data$index_data)) {
  cat("\nIndex Data:\n")
  cat("- Records:", nrow(cached_data$index_data), "\n")
  cat("- Date range:", as.character(min(cached_data$index_data$TIMESTAMP)), "to", as.character(max(cached_data$index_data$TIMESTAMP)), "\n")
  cat("- Unique indices:", length(unique(cached_data$index_data$SYMBOL)), "\n")
  cat("- Latest date:", as.character(max(cached_data$index_data$TIMESTAMP)), "\n")
} else {
  cat("\nIndex Data: ❌ Failed to load\n")
}

cat("\n✅ NSE data loading completed!\n")
cat("📁 Data cached in project directory for analysis scripts\n")
cat("🔄 Run this script regularly to keep data up to date\n")

# =============================================================================
# End of Script
# =============================================================================

