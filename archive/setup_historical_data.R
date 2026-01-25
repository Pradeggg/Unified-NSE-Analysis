# =============================================================================
# SETUP HISTORICAL DATA FOR BACKTESTING
# =============================================================================
# This script helps set up the historical data file for backtesting

library(dplyr)

# =============================================================================
# SETUP FUNCTIONS
# =============================================================================

# Function to check for historical data file
check_historical_data <- function() {
  cat("Checking for historical data file...\n")
  cat("============================================================\n")
  
  # Check various possible locations
  possible_paths <- c(
    "NSE-index/nse_sec_full_data.csv",
    "nse_sec_full_data.csv",
    "../NSE-index/nse_sec_full_data.csv",
    "data/nse_sec_full_data.csv",
    "historical_data/nse_sec_full_data.csv"
  )
  
  found_files <- c()
  
  for(path in possible_paths) {
    if(file.exists(path)) {
      found_files <- c(found_files, path)
      cat("✓ Found:", path, "\n")
      
      # Get file info
      file_info <- file.info(path)
      cat("  Size:", round(file_info$size / 1024 / 1024, 2), "MB\n")
      cat("  Last modified:", file_info$mtime, "\n")
      
      # Try to read a sample
      tryCatch({
        sample_data <- read.csv(path, nrows = 5, stringsAsFactors = FALSE)
        cat("  Columns:", paste(colnames(sample_data), collapse = ", "), "\n")
        cat("  Sample rows:", nrow(sample_data), "\n")
      }, error = function(e) {
        cat("  Error reading file:", e$message, "\n")
      })
    } else {
      cat("✗ Not found:", path, "\n")
    }
  }
  
  if(length(found_files) == 0) {
    cat("\n❌ No historical data file found!\n")
    cat("\nTo set up historical data for backtesting:\n")
    cat("1. Download nse_sec_full_data.csv from the SharePoint link:\n")
    cat("   https://amedeloitte-my.sharepoint.com/:x:/r/personal/pgorai_deloitte_com/Documents/Documents/Data%20Visualization/Analytics/Financial%20Markets/NSE-index/nse_sec_full_data.csv\n")
    cat("2. Place the file in one of these locations:\n")
    cat("   - NSE-index/nse_sec_full_data.csv (recommended)\n")
    cat("   - nse_sec_full_data.csv (in current directory)\n")
    cat("   - data/nse_sec_full_data.csv\n")
    cat("3. Run this script again to verify the setup\n")
  } else {
    cat("\n✅ Historical data file(s) found!\n")
    cat("You can now run: source('historical_data_backtesting.R'); run_historical_data_backtesting()\n")
  }
  
  return(found_files)
}

# Function to create directory structure
create_directory_structure <- function() {
  cat("Creating directory structure for historical data...\n")
  
  # Create NSE-index directory
  if(!dir.exists("NSE-index")) {
    dir.create("NSE-index", recursive = TRUE)
    cat("✓ Created NSE-index directory\n")
  } else {
    cat("✓ NSE-index directory already exists\n")
  }
  
  # Create data directory if it doesn't exist
  if(!dir.exists("data")) {
    dir.create("data", recursive = TRUE)
    cat("✓ Created data directory\n")
  } else {
    cat("✓ Data directory already exists\n")
  }
  
  cat("Directory structure ready!\n")
}

# Function to validate historical data file
validate_historical_data <- function(file_path) {
  cat("Validating historical data file:", file_path, "\n")
  
  tryCatch({
    # Read the file
    data <- read.csv(file_path, stringsAsFactors = FALSE, nrows = 1000)
    
    cat("✓ File loaded successfully\n")
    cat("Sample data structure:\n")
    cat("  Rows:", nrow(data), "\n")
    cat("  Columns:", ncol(data), "\n")
    cat("  Column names:", paste(colnames(data), collapse = ", "), "\n")
    
    # Check for required columns
    required_cols <- c("SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME")
    missing_cols <- setdiff(required_cols, colnames(data))
    
    if(length(missing_cols) > 0) {
      cat("❌ Missing required columns:", paste(missing_cols, collapse = ", "), "\n")
      return(FALSE)
    } else {
      cat("✓ All required columns present\n")
    }
    
    # Check data types
    cat("Data types:\n")
    for(col in required_cols) {
      cat("  ", col, ":", class(data[[col]]), "\n")
    }
    
    # Check for unique stocks
    unique_stocks <- length(unique(data$SYMBOL))
    cat("✓ Unique stocks:", unique_stocks, "\n")
    
    # Check date range
    if("TIMESTAMP" %in% colnames(data)) {
      dates <- as.Date(data$TIMESTAMP)
      cat("✓ Date range:", min(dates, na.rm = TRUE), "to", max(dates, na.rm = TRUE), "\n")
    }
    
    return(TRUE)
    
  }, error = function(e) {
    cat("❌ Error validating file:", e$message, "\n")
    return(FALSE)
  })
}

# Function to provide setup instructions
provide_setup_instructions <- function() {
  cat("\n" , "=", 60, "\n")
  cat("HISTORICAL DATA SETUP INSTRUCTIONS\n")
  cat("=", 60, "\n")
  
  cat("\n1. DOWNLOAD THE HISTORICAL DATA FILE:\n")
  cat("   - Go to the SharePoint link:\n")
  cat("     https://amedeloitte-my.sharepoint.com/:x:/r/personal/pgorai_deloitte_com/Documents/Documents/Data%20Visualization/Analytics/Financial%20Markets/NSE-index/nse_sec_full_data.csv\n")
  cat("   - Download the nse_sec_full_data.csv file\n")
  
  cat("\n2. PLACE THE FILE IN THE CORRECT LOCATION:\n")
  cat("   - Create a folder named 'NSE-index' in your current directory\n")
  cat("   - Place nse_sec_full_data.csv inside the NSE-index folder\n")
  cat("   - The final path should be: NSE-index/nse_sec_full_data.csv\n")
  
  cat("\n3. VERIFY THE SETUP:\n")
  cat("   - Run: source('setup_historical_data.R'); check_historical_data()\n")
  cat("   - This will validate that the file is properly placed and readable\n")
  
  cat("\n4. RUN BACKTESTING:\n")
  cat("   - Once the file is set up, run:\n")
  cat("     source('historical_data_backtesting.R'); run_historical_data_backtesting()\n")
  
  cat("\n5. EXPECTED FILE STRUCTURE:\n")
  cat("   The CSV file should contain these columns:\n")
  cat("   - SYMBOL: Stock symbol (e.g., 'RELIANCE')\n")
  cat("   - TIMESTAMP: Date (YYYY-MM-DD format)\n")
  cat("   - OPEN: Opening price\n")
  cat("   - HIGH: High price\n")
  cat("   - LOW: Low price\n")
  cat("   - CLOSE: Closing price\n")
  cat("   - VOLUME: Trading volume\n")
  
  cat("\n6. ALTERNATIVE LOCATIONS:\n")
  cat("   If you prefer, you can also place the file in:\n")
  cat("   - nse_sec_full_data.csv (current directory)\n")
  cat("   - data/nse_sec_full_data.csv\n")
  
  cat("\n" , "=", 60, "\n")
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

cat("Historical data setup script loaded successfully!\n")
cat("Use check_historical_data() to verify your setup\n")
cat("Use provide_setup_instructions() for detailed instructions\n")

# Run the check if called directly
if(interactive()) {
  cat("Running historical data setup check...\n")
  
  # Create directory structure
  create_directory_structure()
  
  # Check for historical data
  found_files <- check_historical_data()
  
  if(length(found_files) > 0) {
    cat("\nValidating the first found file...\n")
    validate_historical_data(found_files[1])
  } else {
    cat("\nNo historical data files found. Providing setup instructions...\n")
    provide_setup_instructions()
  }
}
