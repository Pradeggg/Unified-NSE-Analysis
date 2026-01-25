# =============================================================================
# BUILD 30-DAY HISTORICAL DATA FOR NSE ANALYSIS
# This script runs the analysis for the last 30 days to build comprehensive historical data
# =============================================================================

suppressMessages({
  library(dplyr)
  library(TTR)
  library(readr)
  library(lubridate)
  library(RSQLite)
  library(DBI)
})

# Set working directory
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')

# Database configuration
db_path <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data/nse_analysis.db'

cat("🚀 BUILDING 30-DAY HISTORICAL DATA FOR NSE ANALYSIS\n")
cat("==================================================\n\n")

# Source the main analysis script
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts/fixed_nse_universe_analysis.R')

# Function to get available dates from the data
get_available_dates <- function() {
  cat("📅 Getting available dates from NSE data...\n")
  
  # Load the stock data to get available dates
  if(!file.exists('nse_sec_full_data.csv')) {
    stop("nse_sec_full_data.csv not found in current directory")
  }
  
  # Read the file to get available dates
  dt_stocks <- read_csv('nse_sec_full_data.csv', 
                       col_types = cols(.default = "c"),
                       locale = locale(encoding = "UTF-8"),
                       show_col_types = FALSE)
  
  # Get unique dates
  dt_stocks$TIMESTAMP <- as.Date(dt_stocks$TIMESTAMP)
  available_dates <- sort(unique(dt_stocks$TIMESTAMP), decreasing = TRUE)
  
  cat("Found", length(available_dates), "available dates\n")
  cat("Date range:", min(available_dates), "to", max(available_dates), "\n")
  
  return(available_dates)
}

# Function to check what dates are already in database
get_existing_dates <- function(db_path) {
  cat("🗄️ Checking existing dates in database...\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Check if tables exist
  tables <- dbListTables(conn)
  if(length(tables) == 0) {
    dbDisconnect(conn)
    return(character(0))
  }
  
  # Get existing dates from market_breadth table
  if("market_breadth" %in% tables) {
    existing_dates <- dbGetQuery(conn, "SELECT DISTINCT analysis_date FROM market_breadth ORDER BY analysis_date DESC")
    existing_dates <- as.Date(existing_dates$analysis_date)
  } else {
    existing_dates <- character(0)
  }
  
  dbDisconnect(conn)
  
  cat("Found", length(existing_dates), "existing dates in database\n")
  if(length(existing_dates) > 0) {
    cat("Existing date range:", min(existing_dates), "to", max(existing_dates), "\n")
  }
  
  return(existing_dates)
}

# Function to run analysis for a specific date
run_analysis_for_date <- function(analysis_date) {
  cat("📊 Running analysis for date:", as.character(analysis_date), "\n")
  
  # Set the analysis date globally
  assign("target_analysis_date", analysis_date, envir = .GlobalEnv)
  
  # Source and run the main analysis script
  # We'll modify the main script to accept a specific date
  source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts/fixed_nse_universe_analysis.R')
  
  cat("✅ Analysis completed for", as.character(analysis_date), "\n\n")
}

# Main execution
cat("🔍 STEP 1: Analyzing available data...\n")
available_dates <- get_available_dates()
existing_dates <- get_existing_dates(db_path)

# Get the last 30 days of available data
last_30_days <- head(available_dates, 30)
cat("📅 Last 30 available dates:\n")
print(last_30_days)

# Find dates that need analysis
dates_to_analyze <- setdiff(last_30_days, existing_dates)
cat("\n📋 Dates to analyze:", length(dates_to_analyze), "out of", length(last_30_days), "\n")

if(length(dates_to_analyze) > 0) {
  cat("New dates to process:\n")
  print(dates_to_analyze)
  
  cat("\n🚀 STEP 2: Running analysis for missing dates...\n")
  
  # Process each date
  for(i in seq_along(dates_to_analyze)) {
    date_to_process <- dates_to_analyze[i]
    cat("\n", paste(rep("=", 60), collapse=""), "\n")
    cat("Processing date", i, "of", length(dates_to_analyze), ":", as.character(date_to_process), "\n")
    cat(paste(rep("=", 60), collapse=""), "\n")
    
    tryCatch({
      run_analysis_for_date(date_to_process)
    }, error = function(e) {
      cat("❌ Error processing date", as.character(date_to_process), ":", e$message, "\n")
    })
  }
  
  cat("\n✅ STEP 3: Historical data build completed!\n")
  cat("Processed", length(dates_to_analyze), "new dates\n")
} else {
  cat("\n✅ All 30 days of data already exist in database!\n")
}

# Final summary
cat("\n📊 FINAL SUMMARY:\n")
cat("================\n")
final_existing_dates <- get_existing_dates(db_path)
cat("Total dates in database:", length(final_existing_dates), "\n")
if(length(final_existing_dates) > 0) {
  cat("Date range:", min(final_existing_dates), "to", max(final_existing_dates), "\n")
}

cat("\n🎉 30-day historical data build completed successfully!\n")
cat("Ready for trend analysis and enhanced dashboard generation.\n")
