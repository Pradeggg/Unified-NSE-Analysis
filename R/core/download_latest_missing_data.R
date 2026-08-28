#!/usr/bin/env Rscript

# =============================================================================
# Download Latest Missing NSE Data
# =============================================================================
# This script downloads the latest missing NSE data since the last load date
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(lubridate)
  library(httr)
})

cat("=== DOWNLOADING LATEST MISSING NSE DATA ===\n")
cat("Date:", format(Sys.Date(), "%B %d, %Y"), "\n\n")

# Set working directory to NSE data location
nse_data_path <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index"
setwd(nse_data_path)

# Function to check if a date is a trading day (Monday to Friday)
is_trading_day <- function(date) {
  wday(date) %in% 2:6  # Monday = 2, Friday = 6
}

# Function to get missing dates since last load
get_missing_dates <- function() {
  # Check current data status
  if(file.exists("nse_sec_full_data.csv")) {
    current_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
    current_data$TIMESTAMP <- as.Date(current_data$TIMESTAMP)
    
    latest_date <- max(current_data$TIMESTAMP, na.rm = TRUE)
    cat("Current latest date in data:", as.character(latest_date), "\n")
    
    # Generate dates from latest_date + 1 to today
    all_dates <- seq(latest_date + 1, Sys.Date(), by = "day")
    
    # Filter for trading days only
    trading_dates <- all_dates[sapply(all_dates, is_trading_day)]
    
    cat("Missing trading dates to download:", length(trading_dates), "\n")
    if(length(trading_dates) > 0) {
      cat("Dates:", paste(trading_dates, collapse = ", "), "\n")
    }
    
    return(trading_dates)
  } else {
    cat("❌ nse_sec_full_data.csv not found\n")
    return(c())
  }
}

# Function to download stock data for a specific date
download_stock_data_for_date <- function(target_date) {
  cat("=== Downloading stock data for", as.character(target_date), "===\n")
  
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
    
    if(response$status_code == 200) {
      # Extract the Pd*.csv file
      unzip(tempzip, tempfilename, overwrite = TRUE)
      
      if(file.exists(tempfilename)) {
        # Read the data
        raw_data <- read.csv(tempfilename, stringsAsFactors = FALSE)
        
        # Filter for equity stocks only
        stock_data <- raw_data %>% 
          filter(SERIES == "EQ" & !is.na(SYMBOL) & SYMBOL != " " & SYMBOL != "")
        
        if(nrow(stock_data) > 0) {
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
          
          # Read existing data and append
          if(file.exists("nse_sec_full_data.csv")) {
            existing_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
            combined_data <- rbind(existing_data, processed_data)
            # Remove duplicates
            combined_data <- combined_data %>%
              distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
          } else {
            combined_data <- processed_data
          }
          
          # Write back to file
          write.csv(combined_data, "nse_sec_full_data.csv", row.names = FALSE)
          cat("✅ Successfully downloaded", nrow(processed_data), "stock records for", as.character(target_date), "\n")
          
          # Clean up temporary files
          if(file.exists(tempfilename)) file.remove(tempfilename)
          if(file.exists(tempzip)) file.remove(tempzip)
          
          return(TRUE)
        } else {
          cat("❌ No equity data found for", as.character(target_date), "\n")
          return(FALSE)
        }
      } else {
        cat("❌ Could not extract data file for", as.character(target_date), "\n")
        return(FALSE)
      }
    } else {
      cat("❌ Download failed for", as.character(target_date), "- Status code:", response$status_code, "\n")
      return(FALSE)
    }
  }, error = function(e) {
    cat("❌ Error downloading stock data for", as.character(target_date), ":", e$message, "\n")
    return(FALSE)
  })
}

# Function to download index data for a specific date
download_index_data_for_date <- function(target_date) {
  cat("=== Downloading index data for", as.character(target_date), "===\n")
  
  tryCatch({
    # Convert date to proper string format
    date_str <- format(target_date, "%Y-%m-%d")
    
    # Use the working NSE URL pattern: PR folder with capital PR + DDMMYY format
    urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                    toupper(format(target_date, "%d%m%y")), ".zip", sep = "")
    tempzip <- paste0("PR", toupper(format(target_date, "%d%m%y")), ".zip", sep = "")
    tempfilename <- paste("Pr", toupper(format(target_date, "%d%m%y")), ".csv", sep = "")
    
    cat("Downloading index data from:", urllink, "\n")
    
    # Download using GET with User-Agent header
    response <- httr::GET(urllink, 
                         httr::write_disk(tempzip, overwrite = TRUE),
                         httr::add_headers(`User-Agent` = "Mozilla/5.0"))
    
    if(response$status_code == 200) {
      # Extract the Pr*.csv file (index data file)
      unzip(tempzip, tempfilename, overwrite = TRUE)
      
      if(file.exists(tempfilename)) {
        # Read the data
        raw_data <- read.csv(tempfilename, stringsAsFactors = FALSE)
        
        # Filter for index data only (IND_SEC=="Y" & MKT == "Y")
        index_data <- raw_data %>% 
          filter(IND_SEC == "Y" & MKT == "Y" & !is.na(SECURITY) & SECURITY != " " & SECURITY != "")
        
        if(nrow(index_data) > 0) {
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
          
          # Read existing data and append
          if(file.exists("nse_index_data.csv")) {
            existing_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
            combined_data <- rbind(existing_data, processed_data)
            # Remove duplicates
            combined_data <- combined_data %>%
              distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
          } else {
            combined_data <- processed_data
          }
          
          # Write back to file
          write.csv(combined_data, "nse_index_data.csv", row.names = FALSE)
          cat("✅ Successfully downloaded", nrow(processed_data), "index records for", as.character(target_date), "\n")
          
          # Clean up temporary files
          if(file.exists(tempfilename)) file.remove(tempfilename)
          if(file.exists(tempzip)) file.remove(tempzip)
          
          return(TRUE)
        } else {
          cat("❌ No index data found for", as.character(target_date), "\n")
          return(FALSE)
        }
      } else {
        cat("❌ Could not extract index data file for", as.character(target_date), "\n")
        return(FALSE)
      }
    } else {
      cat("❌ Download failed for index data on", as.character(target_date), "- Status code:", response$status_code, "\n")
      return(FALSE)
    }
  }, error = function(e) {
    cat("❌ Error downloading index data for", as.character(target_date), ":", e$message, "\n")
    return(FALSE)
  })
}

# Main execution
cat("Getting missing dates...\n")
missing_dates <- get_missing_dates()

if(length(missing_dates) > 0) {
  cat("\n=== DOWNLOADING MISSING DATA ===\n")
  
  successful_downloads <- 0
  
  for(date in missing_dates) {
    cat("\n==================================================\n")
    cat("Processing date:", as.character(date), "\n")
    cat("==================================================\n")
    
    # Download stock data
    stock_success <- download_stock_data_for_date(date)
    
    # Download index data
    index_success <- download_index_data_for_date(date)
    
    if(stock_success || index_success) {
      successful_downloads <- successful_downloads + 1
    }
    
    # Add a small delay between downloads
    Sys.sleep(2)
  }
  
  cat("\n=== DOWNLOAD SUMMARY ===\n")
  cat("Total dates processed:", length(missing_dates), "\n")
  cat("Successful downloads:", successful_downloads, "\n")
  
} else {
  cat("✅ No missing dates found. Data is up to date!\n")
}

# Update project cache
cat("\n=== UPDATING PROJECT CACHE ===\n")
project_data_dir <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data"

# Load updated data
if(file.exists("nse_sec_full_data.csv")) {
  stock_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
  stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)
  save(stock_data, file = file.path(project_data_dir, "nse_stock_cache.RData"))
  cat("✅ Stock data cache updated\n")
}

if(file.exists("nse_index_data.csv")) {
  index_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
  index_data$TIMESTAMP <- as.Date(index_data$TIMESTAMP)
  save(index_data, file = file.path(project_data_dir, "nse_index_cache.RData"))
  cat("✅ Index data cache updated\n")
}

# Create updated summary
summary_data <- list(
  timestamp = Sys.time(),
  stock_records = if(exists("stock_data")) nrow(stock_data) else 0,
  index_records = if(exists("index_data")) nrow(index_data) else 0,
  stock_date_range = if(exists("stock_data")) {
    c(as.character(min(stock_data$TIMESTAMP)), as.character(max(stock_data$TIMESTAMP)))
  } else c(NA, NA),
  index_date_range = if(exists("index_data")) {
    c(as.character(min(index_data$TIMESTAMP)), as.character(max(index_data$TIMESTAMP)))
  } else c(NA, NA),
  unique_stocks = if(exists("stock_data")) length(unique(stock_data$SYMBOL)) else 0,
  unique_indices = if(exists("index_data")) length(unique(index_data$SYMBOL)) else 0
)

write_json(summary_data, file.path(project_data_dir, "data_summary.json"), pretty = TRUE)
cat("✅ Data summary updated\n")

cat("\n=== FINAL SUMMARY ===\n")
if(exists("stock_data")) {
  cat("Stock Data:\n")
  cat("- Records:", nrow(stock_data), "\n")
  cat("- Date range:", as.character(min(stock_data$TIMESTAMP)), "to", as.character(max(stock_data$TIMESTAMP)), "\n")
  cat("- Unique stocks:", length(unique(stock_data$SYMBOL)), "\n")
}

if(exists("index_data")) {
  cat("\nIndex Data:\n")
  cat("- Records:", nrow(index_data), "\n")
  cat("- Date range:", as.character(min(index_data$TIMESTAMP)), "to", as.character(max(index_data$TIMESTAMP)), "\n")
  cat("- Unique indices:", length(unique(index_data$SYMBOL)), "\n")
}

cat("\n✅ Data download completed!\n")
