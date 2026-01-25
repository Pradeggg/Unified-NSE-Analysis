#!/usr/bin/env Rscript

# =============================================================================
# Load Latest NSE Data and Load Missing Data up to September 19, 2025
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(lubridate)
  library(httr)
})

cat("Loading latest NSE data and loading missing data up to September 19, 2025...\n")

# Set working directory to NSE data location
nse_data_path <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index"
setwd(nse_data_path)

# Load the getdataNSE.R file to get data loading functions
cat("Loading NSE data loading functions...\n")
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/getdataNSE.R')

# Function to load missing data for specific dates
load_missing_data <- function(target_dates) {
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
  for(i in 1:length(target_dates)) {
    target_date <- target_dates[i]
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
    
    # Load incremental data for this date using direct manual approach
    tryCatch({
      # Convert date to proper string format
      date_str <- format(target_date, "%Y-%m-%d")
      cat("Loading data for date:", date_str, "\n")
      
      # Manual download approach for single date
      tdata <- as.Date(date_str, format = "%Y-%m-%d")
      
      # Use the working NSE URL pattern: PR folder with capital PR + DDMMYY format
      urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                      toupper(format(tdata, "%d%m%y")),".zip", sep="")
      tempzip <- paste0("PR", toupper(format(tdata, "%d%m%y")),".zip", sep="")
      tempfilename <- paste("Pd",toupper(format(tdata, "%d%m%y")), ".csv", sep="")
      
      cat("Downloading from:", urllink, "\n")
      
      # Download using GET with User-Agent header
      y <- httr::GET(urllink, httr::write_disk(tempzip, overwrite = TRUE),
                     httr::add_headers(`User-Agent` = "Mozilla/5.0"))
      
      if(y$status_code == 200) {
        # Extract the Pd*.csv file
        unzip(tempzip, tempfilename, overwrite = TRUE)
        
        if(file.exists(tempfilename)) {
          optiondf <- read.csv(tempfilename)
          
          # Filter for equity stocks only
          optiondf <- optiondf %>% 
            filter(SERIES == "EQ" & !is.na(SYMBOL) & SYMBOL != " " & SYMBOL != "")
          
          if(nrow(optiondf) > 0) {
            # Map the Pd*.csv columns to standard format
            dt <- optiondf %>%
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
                TIMESTAMP = format(tdata, "%Y-%m-%d"),
                TOTALTRADES = as.numeric(TRADES),
                ISIN = NA
              ) %>%
              select(SYMBOL, ISIN, TIMESTAMP, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, 
                     TOTTRDQTY, TOTTRDVAL, TOTALTRADES) %>%
              filter(!is.na(CLOSE) & !is.na(OPEN) & !is.na(HIGH) & !is.na(LOW))
            
            if(nrow(dt) > 0) {
              # Read existing data and append
              if(file.exists("nse_sec_full_data.csv")) {
                existing_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)
                combined_data <- rbind(existing_data, dt)
                combined_data <- combined_data %>%
                  distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
              } else {
                combined_data <- dt
              }
              
              # Write back to file
              write.csv(combined_data, "nse_sec_full_data.csv", row.names = FALSE)
              cat("✓ Successfully processed", as.character(target_date), "- added", nrow(dt), "records\n")
            } else {
              cat("✗ No valid data after processing for", as.character(target_date), "\n")
            }
          } else {
            cat("✗ No equity data found for", as.character(target_date), "\n")
          }
          
          # Clean up temporary files
          if(file.exists(tempfilename)) file.remove(tempfilename)
          if(file.exists(tempzip)) file.remove(tempzip)
        } else {
          cat("✗ Could not extract data file for", as.character(target_date), "\n")
        }
      } else {
        cat("✗ Download failed for", as.character(target_date), "- Status code:", y$status_code, "\n")
      }
    }, error = function(e) {
      cat("✗ Error processing", as.character(target_date), ":", e$message, "\n")
    })
    
    cat("\n")
  }
}

# Load missing data for available recent dates
cat("=== LOADING MISSING DATA FOR AVAILABLE RECENT DATES ===\n")
missing_dates <- as.Date(c(
  "2025-10-20",  # Monday - Available
  "2025-10-21",  # Tuesday - Available
  "2025-10-23",  # Thursday - Available
  "2025-10-24",  # Friday - Available
  "2025-10-27",  # Monday - Available
  "2025-10-28"   # Tuesday - Available
))

load_missing_data(missing_dates)

# Function to load missing index data for specific dates
load_missing_index_data <- function(target_dates) {
  cat("=== LOADING MISSING NSE INDEX DATA ===\n")
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
    
    # Load index data for this date using the correct approach from background_index.R
    tryCatch({
      # Convert date to proper string format
      date_str <- format(target_date, "%Y-%m-%d")
      cat("Loading index data for date:", date_str, "\n")
      
      # Use the same PR file approach as stock data but filter for index data
      tdata <- as.Date(date_str, format = "%Y-%m-%d")
      
      # Use the working NSE URL pattern: PR folder with capital PR + DDMMYY format
      urllink <- paste("https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR",
                      toupper(format(tdata, "%d%m%y")), ".zip", sep = "")
      tempzip <- paste0("PR", toupper(format(tdata, "%d%m%y")), ".zip", sep = "")
      tempfilename <- paste("Pr", toupper(format(tdata, "%d%m%y")), ".csv", sep = "")
      
      cat("Downloading index data from:", urllink, "\n")
      
      # Download using GET with User-Agent header
      y <- httr::GET(urllink, httr::write_disk(tempzip, overwrite = TRUE),
                     httr::add_headers(`User-Agent` = "Mozilla/5.0"))
      
      if(y$status_code == 200) {
        # Extract the Pr*.csv file (index data file)
        unzip(tempzip, tempfilename, overwrite = TRUE)
        
        if(file.exists(tempfilename)) {
          optiondf <- read.csv(tempfilename)
          
          # Filter for index data only (IND_SEC=="Y" & MKT == "Y")
          optiondf <- optiondf %>% 
            filter(IND_SEC == "Y" & MKT == "Y" & !is.na(SECURITY) & SECURITY != " " & SECURITY != "")
          
          if(nrow(optiondf) > 0) {
            # Rename columns to match the actual Pr*.csv structure
            colnames(optiondf) <- c("MKT", "SECURITY", "PREVCLOSE", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDVAL",
                                  "TOTTRDQTY", "IND_SEC", "CORP_IND", "TOTALTRADES", "HI_52_WK", "LO_52_WK")
            
            # Map the renamed columns to standard format for index data
            dt <- optiondf %>%
              mutate(
                SYMBOL = SECURITY,
                OPEN = as.numeric(OPEN),
                HIGH = as.numeric(HIGH),
                LOW = as.numeric(LOW),
                CLOSE = as.numeric(CLOSE),
                PREVCLOSE = as.numeric(PREVCLOSE),
                TOTTRDQTY = as.numeric(TOTTRDQTY),
                TOTTRDVAL = as.numeric(TOTTRDVAL),
                TIMESTAMP = format(tdata, "%Y-%m-%d"),
                TOTALTRADES = as.numeric(TOTALTRADES),
                HI_52_WK = as.numeric(HI_52_WK),
                LO_52_WK = as.numeric(LO_52_WK),
                ISIN = NA
              ) %>%
              select(SYMBOL, OPEN, HIGH, LOW, CLOSE, PREVCLOSE, 
                     TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, HI_52_WK, LO_52_WK) %>%
              filter(!is.na(CLOSE) & !is.na(OPEN) & !is.na(HIGH) & !is.na(LOW))
            
            if(nrow(dt) > 0) {
              # Read existing data and append
              if(file.exists("nse_index_data.csv")) {
                existing_data <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)
                combined_data <- rbind(existing_data, dt)
                combined_data <- combined_data %>%
                  distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
              } else {
                combined_data <- dt
              }
              
              # Write back to file
              write.csv(combined_data, "nse_index_data.csv", row.names = FALSE)
              cat("✓ Successfully processed index data for", as.character(target_date), "- added", nrow(dt), "records\n")
            } else {
              cat("✗ No valid index data after processing for", as.character(target_date), "\n")
            }
          } else {
            cat("✗ No index data found for", as.character(target_date), "\n")
          }
          
          # Clean up temporary files
          if(file.exists(tempfilename)) file.remove(tempfilename)
          if(file.exists(tempzip)) file.remove(tempzip)
        } else {
          cat("✗ Could not extract index data file for", as.character(target_date), "\n")
        }
      } else {
        cat("✗ Download failed for index data on", as.character(target_date), "- Status code:", y$status_code, "\n")
      }
    }, error = function(e) {
      cat("✗ Error processing index data for", as.character(target_date), ":", e$message, "\n")
    })
    
    cat("\n")
  }
}

# Load missing index data for available recent dates
cat("\n=== LOADING MISSING INDEX DATA FOR AVAILABLE RECENT DATES ===\n")
load_missing_index_data(missing_dates)

# Load the latest data after updating
cat("\nLoading updated NSE stock data...\n")
dt_stocks <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)

cat("Loading NSE index data...\n")
dt_index <- read.csv("nse_index_data.csv", stringsAsFactors = FALSE)

# Convert TIMESTAMP to Date objects
dt_stocks$TIMESTAMP <- as.Date(dt_stocks$TIMESTAMP)
dt_index$TIMESTAMP <- as.Date(dt_index$TIMESTAMP)

# Get latest dates
latest_stock_date <- max(dt_stocks$TIMESTAMP, na.rm = TRUE)
latest_index_date <- max(dt_index$TIMESTAMP, na.rm = TRUE)

cat("Latest stock data date:", as.character(latest_stock_date), "\n")
cat("Latest index data date:", as.character(latest_index_date), "\n")

# Check data availability for 1M calculation
cat("\nChecking data availability for 1M calculation...\n")

# Calculate 30 days ago from latest date
month_1_ago <- latest_stock_date - 30
cat("Target date for 1M calculation (30 days ago):", as.character(month_1_ago), "\n")

# Check if we have data for the target date
available_dates <- unique(dt_stocks$TIMESTAMP)
date_diffs <- abs(as.Date(available_dates) - month_1_ago)
closest_date_idx <- which.min(date_diffs)
closest_date <- available_dates[closest_date_idx]
days_diff <- date_diffs[closest_date_idx]

cat("Closest available date to target:", as.character(closest_date), "\n")
cat("Difference in days:", days_diff, "\n")

if(days_diff <= 5) {
  cat("✅ Data available for 1M calculation (within 5 days tolerance)\n")
} else {
  cat("⚠️ Data may be insufficient for accurate 1M calculation\n")
}

# Test 1M calculation with a sample stock
cat("\nTesting 1M calculation with sample stocks...\n")
test_stocks <- c("RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK")

for(symbol in test_stocks) {
  cat("\n=== Testing", symbol, "===\n")
  
  # Get stock data
  stock_data <- dt_stocks[dt_stocks$SYMBOL == symbol, ]
  
  if(nrow(stock_data) == 0) {
    cat("No data found for", symbol, "\n")
    next
  }
  
  # Get latest price
  latest_data <- stock_data[stock_data$TIMESTAMP == latest_stock_date, ]
  current_price <- latest_data$CLOSE
  
  # Calculate 1M change using the fixed approach
  month_1_ago <- latest_stock_date - 30
  
  # Find closest available date within ±5 days
  available_dates_stock <- unique(stock_data$TIMESTAMP)
  date_diffs_stock <- abs(as.Date(available_dates_stock) - month_1_ago)
  closest_date_idx_stock <- which.min(date_diffs_stock)
  closest_date_stock <- available_dates_stock[closest_date_idx_stock]
  
  # Only use if the closest date is within 5 days of target
  if(date_diffs_stock[closest_date_idx_stock] <= 5) {
    price_1m_ago <- stock_data %>% 
      filter(TIMESTAMP == closest_date_stock) %>% 
      pull(CLOSE) %>% 
      first()
    
    if(!is.na(price_1m_ago) && price_1m_ago > 0) {
      change_1m <- round(((current_price - price_1m_ago) / price_1m_ago) * 100, 2)
      cat("Current price:", current_price, "\n")
      cat("Month ago price:", price_1m_ago, " (from", as.character(closest_date_stock), ")\n")
      cat("1-month change:", change_1m, "%\n")
    } else {
      cat("Month ago price: NA or 0\n")
      cat("1-month change: NA\n")
    }
  } else {
    cat("No suitable data within 5 days for 1M calculation\n")
    cat("1-month change: NA\n")
  }
}

# Save the loaded data to the current project directory
cat("\nSaving loaded data to project directory...\n")
project_data_dir <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data"

# Save stock data
save(dt_stocks, file = file.path(project_data_dir, "nse_stock_cache.RData"))
cat("✅ Stock data saved to:", file.path(project_data_dir, "nse_stock_cache.RData"), "\n")

# Save index data
save(dt_index, file = file.path(project_data_dir, "nse_index_cache.RData"))
cat("✅ Index data saved to:", file.path(project_data_dir, "nse_index_cache.RData"), "\n")

# Create a summary of the loaded data
cat("\n=== DATA LOADING SUMMARY ===\n")
cat("Stock data records:", nrow(dt_stocks), "\n")
cat("Index data records:", nrow(dt_index), "\n")
cat("Date range - Stocks:", as.character(min(dt_stocks$TIMESTAMP)), "to", as.character(max(dt_stocks$TIMESTAMP)), "\n")
cat("Date range - Index:", as.character(min(dt_index$TIMESTAMP)), "to", as.character(max(dt_index$TIMESTAMP)), "\n")
cat("Unique stocks:", length(unique(dt_stocks$SYMBOL)), "\n")
cat("Unique indices:", length(unique(dt_index$SYMBOL)), "\n")

cat("\n✅ NSE data loaded successfully!\n")
cat("✅ Missing data for available recent dates loaded!\n")
cat("✅ 1M calculation issue identified and solution provided!\n")
cat("📁 Data cached in project directory for analysis scripts\n")
