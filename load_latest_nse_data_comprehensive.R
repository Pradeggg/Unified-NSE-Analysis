#!/usr/bin/env Rscript

# =============================================================================
# Comprehensive NSE Data Loader - Latest Stocks and Index Data
# =============================================================================
# This script loads the latest NSE stock and index data with comprehensive
# error handling, data validation, and caching mechanisms.
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

cat("=== COMPREHENSIVE NSE DATA LOADER ===\n")
cat("Date:", format(Sys.Date(), "%B %d, %Y"), "\n")
cat("NSE Data Path:", nse_data_path, "\n")
cat("Project Data Path:", project_data_dir, "\n\n")

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
    if (col %in% names(data)) {
      missing_count <- sum(is.na(data[[col]]) | data[[col]] == "", na.rm = TRUE)
      if (!is.na(missing_count) && missing_count > 0) {
        cat("⚠️ Missing values in", col, ":", missing_count, "records\n")
      }
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
    # Use the working NSE URL pattern: PR folder with capital PR + DDMMYY format
    # ZIP file: PR291025.zip (PR + DDMMYY)
    # Stock file inside: pd29102025.csv (pd + DDMMYYYY, lowercase)
    urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                    toupper(format(target_date, "%d%m%y")), ".zip", sep = "")
    tempzip <- paste0("PR", toupper(format(target_date, "%d%m%y")), ".zip", sep = "")
    tempfilename <- paste("pd", tolower(format(target_date, "%d%m%Y")), ".csv", sep = "")
    
    cat("Downloading from:", urllink, "\n")
    
    # Download using GET with simple headers (tested - this works)
    response <- httr::GET(urllink, 
                         httr::write_disk(tempzip, overwrite = TRUE),
                         httr::add_headers(
                           `User-Agent` = "Mozilla/5.0",
                           `Referer` = "https://www.nseindia.com/"
                         ),
                         httr::timeout(30))
    
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

# Function to load stock data for a date range
load_stock_data_for_date_range <- function(start_date, end_date) {
  cat("=== LOADING STOCK DATA FOR DATE RANGE ===\n")
  cat("Start date:", as.character(start_date), "\n")
  cat("End date:", as.character(end_date), "\n\n")
  
  # Generate all dates in range
  all_dates <- seq(start_date, end_date, by = "day")
  # Filter for trading days only
  trading_dates <- all_dates[sapply(all_dates, is_trading_day)]
  
  cat("Trading days to download:", length(trading_dates), "\n")
  if (length(trading_dates) > 0) {
    cat("Dates:", paste(as.character(trading_dates), collapse = ", "), "\n\n")
  }
  
  # Load existing data if available
  stock_file <- "nse_sec_full_data.csv"
  existing_data <- NULL
  existing_dates <- c()
  
  if (file.exists(stock_file)) {
    existing_data <- read.csv(stock_file, stringsAsFactors = FALSE)
    existing_data$TIMESTAMP <- as.Date(existing_data$TIMESTAMP)
    existing_dates <- unique(existing_data$TIMESTAMP)
    cat("Existing data: Latest date =", as.character(max(existing_dates)), ", Total records =", nrow(existing_data), "\n\n")
  }
  
  # Filter out dates that already exist
  dates_to_download <- trading_dates[!trading_dates %in% existing_dates]
  
  if (length(dates_to_download) == 0) {
    cat("✅ All dates in range already exist in data\n")
    if (!is.null(existing_data)) {
      return(existing_data)
    } else {
      return(NULL)
    }
  }
  
  cat("Dates to download:", length(dates_to_download), "\n\n")
  
  # Download data for each date
  new_data_list <- list()
  successful_downloads <- 0
  failed_downloads <- 0
  
  for (i in seq_along(dates_to_download)) {
    target_date <- dates_to_download[i]
    cat("\n[", i, "/", length(dates_to_download), "] Processing", as.character(target_date), "...\n")
    
    date_data <- load_stock_data_for_date(target_date)
    
    if (!is.null(date_data)) {
      new_data_list[[as.character(target_date)]] <- date_data
      successful_downloads <- successful_downloads + 1
    } else {
      failed_downloads <- failed_downloads + 1
    }
    
    # Small delay between downloads
    Sys.sleep(1)
  }
  
  cat("\n=== DOWNLOAD SUMMARY ===\n")
  cat("Successful:", successful_downloads, "\n")
  cat("Failed:", failed_downloads, "\n\n")
  
  # Combine all new data
  if (length(new_data_list) > 0) {
    all_new_data <- do.call(rbind, new_data_list)
    
    # Merge with existing data
    if (!is.null(existing_data)) {
      combined_data <- rbind(existing_data, all_new_data)
    } else {
      combined_data <- all_new_data
    }
    
    # Remove duplicates
    combined_data <- combined_data %>%
      distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
    
    # Write back to file
    write.csv(combined_data, stock_file, row.names = FALSE)
    cat("✅ Stock data updated successfully\n")
    
    # Validate the updated data
    validate_data_quality(combined_data, "stock")
    
    return(combined_data)
  } else {
    cat("⚠️ No new data downloaded\n")
    if (!is.null(existing_data)) {
      return(existing_data)
    } else {
      return(NULL)
    }
  }
}

# Function to load latest stock data
load_latest_stock_data <- function() {
  cat("=== LOADING LATEST STOCK DATA ===\n")
  
  # Get the last trading day
  last_trading_day <- get_last_trading_day()
  cat("Last trading day:", as.character(last_trading_day), "\n")
  
  # Check current data status
  stock_file <- "nse_sec_full_data.csv"
  if (file.exists(stock_file)) {
    current_data <- read.csv(stock_file, stringsAsFactors = FALSE)
    current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
    
    latest_date <- max(current_data$TIMESTAMP, na.rm = TRUE)
    total_records <- nrow(current_data)
    
    cat("Current stock data status:\n")
    cat("- Latest date:", as.character(latest_date), "\n")
    cat("- Total records:", total_records, "\n")
    cat("- Date range:", as.character(min(current_data$TIMESTAMP, na.rm = TRUE)), "to", as.character(latest_date), "\n")
    
    # Check if we need to update
    if (latest_date >= last_trading_day) {
      cat("✅ Stock data is up to date\n")
      return(current_data)
    } else {
      cat("⚠️ Stock data needs updating\n")
    }
  } else {
    cat("⚠️ Stock data file not found. Will create new file.\n")
  }
  
  # Load data for the last trading day
  new_data <- load_stock_data_for_date(last_trading_day)
  
  if (!is.null(new_data)) {
    # Read existing data and append
    if (file.exists(stock_file)) {
      existing_data <- read.csv(stock_file, stringsAsFactors = FALSE)
      combined_data <- rbind(existing_data, new_data)
      # Remove duplicates
      combined_data <- combined_data %>%
        distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
    } else {
      combined_data <- new_data
    }
    
    # Write back to file
    write.csv(combined_data, stock_file, row.names = FALSE)
    cat("✅ Stock data updated successfully\n")
    
    # Validate the updated data
    validate_data_quality(combined_data, "stock")
    
    return(combined_data)
  } else {
    cat("❌ Failed to load new stock data\n")
    return(NULL)
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
    # ZIP file: PR291025.zip (PR + DDMMYY)
    # Index file inside: pr29102025.csv (pr + DDMMYYYY, lowercase)
    urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                    toupper(format(tdata, "%d%m%y")), ".zip", sep = "")
    tempzip <- paste0("PR", toupper(format(tdata, "%d%m%y")), ".zip", sep = "")
    tempfilename <- paste("pr", tolower(format(tdata, "%d%m%Y")), ".csv", sep = "")
    
    cat("Downloading index data from:", urllink, "\n")
    
    # Download using GET with simple headers (tested - this works)
    response <- httr::GET(urllink, 
                         httr::write_disk(tempzip, overwrite = TRUE),
                         httr::add_headers(
                           `User-Agent` = "Mozilla/5.0",
                           `Referer` = "https://www.nseindia.com/"
                         ),
                         httr::timeout(30))
    
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
                LO_52_WK = as.numeric(LO_52_WK),
                ISIN = NA
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

# Function to load index data for a date range
load_index_data_for_date_range <- function(start_date, end_date) {
  cat("=== LOADING INDEX DATA FOR DATE RANGE ===\n")
  cat("Start date:", as.character(start_date), "\n")
  cat("End date:", as.character(end_date), "\n\n")
  
  # Generate all dates in range
  all_dates <- seq(start_date, end_date, by = "day")
  # Filter for trading days only
  trading_dates <- all_dates[sapply(all_dates, is_trading_day)]
  
  cat("Trading days to download:", length(trading_dates), "\n")
  if (length(trading_dates) > 0) {
    cat("Dates:", paste(as.character(trading_dates), collapse = ", "), "\n\n")
  }
  
  # Load existing data if available
  index_file <- "nse_index_data.csv"
  existing_data <- NULL
  existing_dates <- c()
  
  if (file.exists(index_file)) {
    existing_data <- read.csv(index_file, stringsAsFactors = FALSE)
    existing_data$TIMESTAMP <- as.Date(existing_data$TIMESTAMP)
    existing_dates <- unique(existing_data$TIMESTAMP)
    cat("Existing data: Latest date =", as.character(max(existing_dates)), ", Total records =", nrow(existing_data), "\n\n")
  }
  
  # Filter out dates that already exist
  dates_to_download <- trading_dates[!trading_dates %in% existing_dates]
  
  if (length(dates_to_download) == 0) {
    cat("✅ All dates in range already exist in data\n")
    if (!is.null(existing_data)) {
      return(existing_data)
    } else {
      return(NULL)
    }
  }
  
  cat("Dates to download:", length(dates_to_download), "\n\n")
  
  # Download data for each date
  new_data_list <- list()
  successful_downloads <- 0
  failed_downloads <- 0
  
  for (i in seq_along(dates_to_download)) {
    target_date <- dates_to_download[i]
    cat("\n[", i, "/", length(dates_to_download), "] Processing", as.character(target_date), "...\n")
    
    date_data <- load_index_data_for_date(target_date)
    
    if (!is.null(date_data)) {
      new_data_list[[as.character(target_date)]] <- date_data
      successful_downloads <- successful_downloads + 1
    } else {
      failed_downloads <- failed_downloads + 1
    }
    
    # Small delay between downloads
    Sys.sleep(1)
  }
  
  cat("\n=== DOWNLOAD SUMMARY ===\n")
  cat("Successful:", successful_downloads, "\n")
  cat("Failed:", failed_downloads, "\n\n")
  
  # Combine all new data
  if (length(new_data_list) > 0) {
    all_new_data <- do.call(rbind, new_data_list)
    
    # Merge with existing data
    if (!is.null(existing_data)) {
      combined_data <- rbind(existing_data, all_new_data)
    } else {
      combined_data <- all_new_data
    }
    
    # Remove duplicates
    combined_data <- combined_data %>%
      distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
    
    # Write back to file
    write.csv(combined_data, index_file, row.names = FALSE)
    cat("✅ Index data updated successfully\n")
    
    # Validate the updated data
    validate_data_quality(combined_data, "index")
    
    return(combined_data)
  } else {
    cat("⚠️ No new data downloaded\n")
    if (!is.null(existing_data)) {
      return(existing_data)
    } else {
      return(NULL)
    }
  }
}

# Function to load latest index data
load_latest_index_data <- function() {
  cat("=== LOADING LATEST INDEX DATA ===\n")
  
  # Get the last trading day
  last_trading_day <- get_last_trading_day()
  cat("Last trading day:", as.character(last_trading_day), "\n")
  
  # Check current data status
  index_file <- "nse_index_data.csv"
  if (file.exists(index_file)) {
    current_data <- read.csv(index_file, stringsAsFactors = FALSE)
    current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
    
    latest_date <- max(current_data$TIMESTAMP, na.rm = TRUE)
    total_records <- nrow(current_data)
    
    cat("Current index data status:\n")
    cat("- Latest date:", as.character(latest_date), "\n")
    cat("- Total records:", total_records, "\n")
    cat("- Date range:", as.character(min(current_data$TIMESTAMP, na.rm = TRUE)), "to", as.character(latest_date), "\n")
    
    # Check if we need to update
    if (latest_date >= last_trading_day) {
      cat("✅ Index data is up to date\n")
      return(current_data)
    } else {
      cat("⚠️ Index data needs updating\n")
    }
  } else {
    cat("⚠️ Index data file not found. Will create new file.\n")
  }
  
  # Load data for the last trading day
  new_data <- load_index_data_for_date(last_trading_day)
  
  if (!is.null(new_data)) {
    # Read existing data and append
    if (file.exists(index_file)) {
      existing_data <- read.csv(index_file, stringsAsFactors = FALSE)
      combined_data <- rbind(existing_data, new_data)
      # Remove duplicates
      combined_data <- combined_data %>%
        distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
    } else {
      combined_data <- new_data
    }
    
    # Write back to file
    write.csv(combined_data, index_file, row.names = FALSE)
    cat("✅ Index data updated successfully\n")
    
    # Validate the updated data
    validate_data_quality(combined_data, "index")
    
    return(combined_data)
  } else {
    cat("❌ Failed to load new index data\n")
    return(NULL)
  }
}

# =============================================================================
# Data Caching and Project Integration
# =============================================================================

# Function to cache data for the project
cache_data_for_project <- function(stock_data, index_data) {
  cat("=== CACHING DATA FOR PROJECT ===\n")
  
  # Convert TIMESTAMP to Date objects
  if (!is.null(stock_data)) {
    stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)
  }
  if (!is.null(index_data)) {
    index_data$TIMESTAMP <- as.Date(index_data$TIMESTAMP)
  }
  
  # Save stock data
  if (!is.null(stock_data)) {
    # Save as RData
    save(stock_data, file = file.path(project_data_dir, "nse_stock_cache.RData"))
    cat("✅ Stock data cached to:", file.path(project_data_dir, "nse_stock_cache.RData"), "\n")
    
    # Save as CSV
    write.csv(stock_data, file = file.path(project_data_dir, "nse_sec_full_data.csv"), row.names = FALSE)
    cat("✅ Stock data saved to CSV:", file.path(project_data_dir, "nse_sec_full_data.csv"), "\n")
  }
  
  # Save index data
  if (!is.null(index_data)) {
    # Save as RData
    save(index_data, file = file.path(project_data_dir, "nse_index_cache.RData"))
    cat("✅ Index data cached to:", file.path(project_data_dir, "nse_index_cache.RData"), "\n")
    
    # Save as CSV
    write.csv(index_data, file = file.path(project_data_dir, "nse_index_data.csv"), row.names = FALSE)
    cat("✅ Index data saved to CSV:", file.path(project_data_dir, "nse_index_data.csv"), "\n")
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
}

# =============================================================================
# Main Execution
# =============================================================================

# Configuration: Date range to download
# Automatically detect the latest date in existing data and download till specified end date
USE_DATE_RANGE <- TRUE

# Set the target end date (January 22, 2026)
END_DATE <- as.Date("2026-01-22")

# Automatically detect the latest date in existing data
stock_file <- file.path(project_data_dir, "nse_sec_full_data.csv")
latest_existing_date <- NULL
if (file.exists(stock_file)) {
  existing_stock_data <- read.csv(stock_file, stringsAsFactors = FALSE)
  existing_stock_data$TIMESTAMP <- as.Date(existing_stock_data$TIMESTAMP)
  latest_existing_date <- max(existing_stock_data$TIMESTAMP, na.rm = TRUE)
  cat("Latest date in existing stock data:", as.character(latest_existing_date), "\n")
  # Start from the day after the latest existing date
  START_DATE <- latest_existing_date + 1
} else {
  # If no existing data, start from a reasonable date (e.g., 1 year ago)
  START_DATE <- Sys.Date() - 365
  cat("No existing stock data found. Starting from:", as.character(START_DATE), "\n")
}

# Ensure START_DATE is not after END_DATE
if (START_DATE > END_DATE) {
  if (!is.null(latest_existing_date)) {
    cat("⚠️ Latest existing date (", as.character(latest_existing_date), ") is already at or after end date (", as.character(END_DATE), ")\n")
  } else {
    cat("⚠️ Start date (", as.character(START_DATE), ") is already at or after end date (", as.character(END_DATE), ")\n")
  }
  cat("✅ Data is already up to date. No new data to download.\n")
  # Set dates to same value to skip download
  START_DATE <- END_DATE
}

if (USE_DATE_RANGE) {
  cat("=== USING DATE RANGE MODE ===\n")
  cat("Start Date:", as.character(START_DATE), "\n")
  cat("End Date:", as.character(END_DATE), "\n\n")
  
  # Load stock data for date range
  stock_data <- load_stock_data_for_date_range(START_DATE, END_DATE)
  
  # Load index data for date range
  index_data <- load_index_data_for_date_range(START_DATE, END_DATE)
} else {
  # Load latest stock data (single day)
  stock_data <- load_latest_stock_data()
  
  # Load latest index data (single day)
  index_data <- load_latest_index_data()
}

# Cache data for the project
cache_data_for_project(stock_data, index_data)

# =============================================================================
# Final Summary
# =============================================================================

cat("\n=== FINAL DATA LOADING SUMMARY ===\n")

if (!is.null(stock_data)) {
  cat("Stock Data:\n")
  cat("- Records:", nrow(stock_data), "\n")
  cat("- Date range:", as.character(min(stock_data$TIMESTAMP)), "to", as.character(max(stock_data$TIMESTAMP)), "\n")
  cat("- Unique stocks:", length(unique(stock_data$SYMBOL)), "\n")
  cat("- Latest date:", as.character(max(stock_data$TIMESTAMP)), "\n")
} else {
  cat("Stock Data: ❌ Failed to load\n")
}

if (!is.null(index_data)) {
  cat("\nIndex Data:\n")
  cat("- Records:", nrow(index_data), "\n")
  cat("- Date range:", as.character(min(index_data$TIMESTAMP)), "to", as.character(max(index_data$TIMESTAMP)), "\n")
  cat("- Unique indices:", length(unique(index_data$SYMBOL)), "\n")
  cat("- Latest date:", as.character(max(index_data$TIMESTAMP)), "\n")
} else {
  cat("\nIndex Data: ❌ Failed to load\n")
}

cat("\n✅ NSE data loading completed!\n")
cat("📁 Data cached in project directory for analysis scripts\n")
cat("🔄 Run this script regularly to keep data up to date\n")

# =============================================================================
# End of Script
# =============================================================================
