# Enhanced NSE Universe Analysis - Optimized and Robust
# Comprehensive analysis with relative strength focus and error handling

suppressMessages({
  library(dplyr)
  library(TTR)
  library(readr)
  library(lubridate)
  library(RSQLite)
  library(DBI)
})

# Set working directory with error handling
# Use project data directory for data files
project_data_dir <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data'
nse_data_dir <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/'

# Try to set working directory to NSE-index for compatibility, but use project data directory for data files
tryCatch({
  setwd(nse_data_dir)
}, error = function(e) {
  print("Warning: Could not set working directory. Using current directory.")
})

# Store the current directory for output files
output_dir <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/reports/'

# Create reports directory if it doesn't exist
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
  cat("Created reports directory:", output_dir, "\n")
}

print("Starting ENHANCED NSE Universe Analysis...")

# Database configuration
db_path <- 'nse_analysis.db'

# =============================================================================
# DATABASE INITIALIZATION AND MANAGEMENT FUNCTIONS
# =============================================================================

# Function to initialize database with required tables
initialize_database <- function(db_path) {
  # Connect to database
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Create stocks_analysis table
  stocks_sql <- "
  CREATE TABLE IF NOT EXISTS stocks_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    company_name TEXT,
    market_cap_category TEXT,
    current_price REAL,
    change_1d REAL,
    change_1w REAL,
    change_1m REAL,
    technical_score REAL,
    rsi REAL,
    trend_signal TEXT,
    relative_strength REAL,
    can_slim_score INTEGER,
    minervini_score INTEGER,
    fundamental_score INTEGER,
    enhanced_fund_score REAL,
    earnings_quality REAL,
    sales_growth REAL,
    financial_strength REAL,
    institutional_backing REAL,
    trading_value REAL,
    trading_signal TEXT,
    UNIQUE(analysis_date, symbol)
  )"
  
  # Create index_analysis table
  index_sql <- "
  CREATE TABLE IF NOT EXISTS index_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    index_name TEXT NOT NULL,
    current_level REAL,
    technical_score REAL,
    rsi REAL,
    momentum_50d REAL,
    relative_strength REAL,
    trend_signal TEXT,
    trading_signal TEXT,
    UNIQUE(analysis_date, index_name)
  )"
  
  # Create market_breadth table
  breadth_sql <- "
  CREATE TABLE IF NOT EXISTS market_breadth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    total_stocks INTEGER,
    strong_buy_count INTEGER,
    buy_count INTEGER,
    hold_count INTEGER,
    weak_hold_count INTEGER,
    sell_count INTEGER,
    bullish_percentage REAL,
    bearish_percentage REAL,
    average_technical_score REAL,
    UNIQUE(analysis_date)
  )"
  
  # Execute table creation
  dbExecute(conn, stocks_sql)
  dbExecute(conn, index_sql)
  dbExecute(conn, breadth_sql)
  
  cat("Database initialized successfully with tables: stocks_analysis, index_analysis, market_breadth\n")
  
  # Close connection
  dbDisconnect(conn)
}

# Function to create database tables
create_database_tables <- function(db_path) {
  cat("Creating database tables...\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Create stocks_analysis table
  stocks_sql <- "
  CREATE TABLE IF NOT EXISTS stocks_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    company_name TEXT,
    market_cap_category TEXT,
    current_price REAL,
    change_1d REAL,
    change_1w REAL,
    change_1m REAL,
    technical_score REAL,
    rsi REAL,
    trend_signal TEXT,
    relative_strength REAL,
    can_slim_score INTEGER,
    minervini_score INTEGER,
    fundamental_score INTEGER,
    enhanced_fund_score REAL,
    earnings_quality REAL,
    sales_growth REAL,
    financial_strength REAL,
    institutional_backing REAL,
    trading_value REAL,
    trading_signal TEXT,
    UNIQUE(analysis_date, symbol)
  )"
  
  # Create index_analysis table
  index_sql <- "
  CREATE TABLE IF NOT EXISTS index_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    index_name TEXT NOT NULL,
    current_level REAL,
    technical_score REAL,
    rsi REAL,
    momentum_50d REAL,
    relative_strength REAL,
    trend_signal TEXT,
    trading_signal TEXT,
    UNIQUE(analysis_date, index_name)
  )"
  
  # Create market_breadth table
  breadth_sql <- "
  CREATE TABLE IF NOT EXISTS market_breadth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    total_stocks INTEGER,
    strong_buy_count INTEGER,
    buy_count INTEGER,
    hold_count INTEGER,
    weak_hold_count INTEGER,
    sell_count INTEGER,
    strong_buy_percent REAL,
    buy_percent REAL,
    hold_percent REAL,
    weak_hold_percent REAL,
    sell_percent REAL,
    market_sentiment TEXT,
    UNIQUE(analysis_date)
  )"
  
  # Execute table creation
  dbExecute(conn, stocks_sql)
  dbExecute(conn, index_sql)
  dbExecute(conn, breadth_sql)
  
  dbDisconnect(conn)
  cat("Database tables created successfully.\n")
}

# Function to save stocks analysis to database
save_stocks_to_database <- function(results, analysis_date, db_path) {
  cat("Saving stocks analysis to database...\n")
  cat("Results data has", nrow(results), "rows\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Begin transaction
  dbBegin(conn)
  
  tryCatch({
    # Prepare data for insertion
    stocks_data <- results %>%
      select(SYMBOL, COMPANY_NAME, MARKET_CAP_CATEGORY, CURRENT_PRICE, CHANGE_1D, CHANGE_1W, CHANGE_1M,
             TECHNICAL_SCORE, RSI, TREND_SIGNAL, RELATIVE_STRENGTH, CAN_SLIM_SCORE, MINERVINI_SCORE,
             FUNDAMENTAL_SCORE, ENHANCED_FUND_SCORE, EARNINGS_QUALITY, SALES_GROWTH, FINANCIAL_STRENGTH,
             INSTITUTIONAL_BACKING, TRADING_VALUE, TRADING_SIGNAL) %>%
      mutate(analysis_date = analysis_date)
    
    # Convert column names to lowercase to match database schema
    colnames(stocks_data) <- tolower(colnames(stocks_data))
    
    cat("Prepared", nrow(stocks_data), "rows for insertion\n")
    
    # Delete existing data for this date first
    dbExecute(conn, "DELETE FROM stocks_analysis WHERE analysis_date = ?", params = list(as.character(analysis_date)))
    
    # Insert new data using dbWriteTable for better performance
    dbWriteTable(conn, "stocks_analysis", stocks_data, append = TRUE)
    
    # Commit transaction
    dbCommit(conn)
    
    # Check final count
    final_count <- dbGetQuery(conn, "SELECT COUNT(*) as count FROM stocks_analysis")
    cat("Successfully saved", nrow(stocks_data), "stocks records to database\n")
    cat("Final count in database:", final_count$count, "\n")
    
  }, error = function(e) {
    dbRollback(conn)
    cat("Error saving stocks data:", e$message, "\n")
  })
  
  dbDisconnect(conn)
}

# Function to save index analysis to database
save_indices_to_database <- function(index_results, analysis_date, db_path) {
  cat("Saving index analysis to database...\n")
  cat("Index results data has", nrow(index_results), "rows\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Begin transaction
  dbBegin(conn)
  
  tryCatch({
    # Prepare data for insertion
    index_data <- index_results %>%
      select(INDEX_NAME, CURRENT_LEVEL, TECHNICAL_SCORE, RSI, MOMENTUM_50D, RELATIVE_STRENGTH, TREND_SIGNAL, TRADING_SIGNAL) %>%
      mutate(analysis_date = analysis_date)
    
    # Convert column names to lowercase to match database schema
    colnames(index_data) <- tolower(colnames(index_data))
    
    cat("Prepared", nrow(index_data), "index rows for insertion\n")
    
    # Delete existing data for this date first
    dbExecute(conn, "DELETE FROM index_analysis WHERE analysis_date = ?", params = list(as.character(analysis_date)))
    
    # Insert new data using dbWriteTable for better performance
    dbWriteTable(conn, "index_analysis", index_data, append = TRUE)
    
    # Commit transaction
    dbCommit(conn)
    
    # Check final count
    final_count <- dbGetQuery(conn, "SELECT COUNT(*) as count FROM index_analysis")
    cat("Successfully saved", nrow(index_data), "index records to database\n")
    cat("Final index count in database:", final_count$count, "\n")
    
  }, error = function(e) {
    dbRollback(conn)
    cat("Error saving index data:", e$message, "\n")
  })
  
  dbDisconnect(conn)
}

# Function to save market breadth to database
save_market_breadth_to_database <- function(results, analysis_date, db_path) {
  cat("Saving market breadth to database...\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Calculate market breadth metrics
  total_stocks <- nrow(results)
  strong_buy_count <- sum(results$TRADING_SIGNAL == "STRONG_BUY")
  buy_count <- sum(results$TRADING_SIGNAL == "BUY")
  hold_count <- sum(results$TRADING_SIGNAL == "HOLD")
  weak_hold_count <- sum(results$TRADING_SIGNAL == "WEAK_HOLD")
  sell_count <- sum(results$TRADING_SIGNAL == "SELL")
  bullish_percentage <- round(((strong_buy_count + buy_count) / total_stocks) * 100, 1)
  bearish_percentage <- round((sell_count / total_stocks) * 100, 1)
  average_technical_score <- round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1)
  
  # Prepare data for insertion
  breadth_data <- data.frame(
    analysis_date = analysis_date,
    total_stocks = total_stocks,
    strong_buy_count = strong_buy_count,
    buy_count = buy_count,
    hold_count = hold_count,
    weak_hold_count = weak_hold_count,
    sell_count = sell_count,
    bullish_percentage = bullish_percentage,
    bearish_percentage = bearish_percentage,
    average_technical_score = average_technical_score
  )
  
  # Insert or replace data
  insert_sql <- "
  INSERT OR REPLACE INTO market_breadth 
  (analysis_date, total_stocks, strong_buy_count, buy_count, hold_count, weak_hold_count, sell_count, 
   bullish_percentage, bearish_percentage, average_technical_score)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
  
  dbExecute(conn, insert_sql, params = unname(as.list(breadth_data)))
  
  cat("Saved market breadth record to database\n")
  dbDisconnect(conn)
}

# Initialize database
initialize_database(db_path)

# Load data with enhanced error handling and validation
print("Loading NSE stock data with enhanced error handling...")
tryCatch({
  # Check if file exists
  # Check project data directory first, then fallback to current directory
  stock_file <- file.path(project_data_dir, 'nse_sec_full_data.csv')
  if(!file.exists(stock_file)) {
    stock_file <- 'nse_sec_full_data.csv'
    if(!file.exists(stock_file)) {
      stop("nse_sec_full_data.csv not found in project data directory or current directory")
    }
  }
  cat("Loading stock data from:", stock_file, "\n")
  
  # Read the file with readr for better handling
  dt_stocks <- read_csv(stock_file, 
                       col_types = cols(.default = "c"),  # Read all as character first
                       locale = locale(encoding = "UTF-8"),
                       show_col_types = FALSE)
  
  # Validate required columns
  required_cols <- c("SYMBOL", "TIMESTAMP", "CLOSE", "OPEN", "HIGH", "LOW", "TOTTRDQTY", "TOTTRDVAL")
  missing_cols <- setdiff(required_cols, names(dt_stocks))
  if(length(missing_cols) > 0) {
    stop(paste("Missing required columns:", paste(missing_cols, collapse = ", ")))
  }
  
  # Clean and convert data types with validation
  dt_stocks <- dt_stocks %>%
    filter(!is.na(SYMBOL) & SYMBOL != "" & !is.na(TIMESTAMP)) %>%
    mutate(
      TIMESTAMP = as.Date(TIMESTAMP),
      CLOSE = as.numeric(CLOSE),
      OPEN = as.numeric(OPEN),
      HIGH = as.numeric(HIGH),
      LOW = as.numeric(LOW),
      TOTTRDQTY = as.numeric(TOTTRDQTY),
      TOTTRDVAL = as.numeric(TOTTRDVAL)
    ) %>%
    filter(!is.na(CLOSE) & !is.na(TIMESTAMP) & CLOSE > 0 & TOTTRDVAL > 0)
  
  # Remove duplicates - keep the record with highest trading value for each SYMBOL-TIMESTAMP combination
  print(paste("Before deduplication:", nrow(dt_stocks), "records"))
  dt_stocks <- dt_stocks %>%
    arrange(SYMBOL, TIMESTAMP, desc(TOTTRDVAL)) %>%
    distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE) %>%
    arrange(TIMESTAMP, SYMBOL)
  
  print(paste("After deduplication:", nrow(dt_stocks), "clean records"))
  
}, error = function(e) {
  print(paste("Error loading with readr:", e$message))
  print("Falling back to base R read.csv...")
  
  tryCatch({
    # Fallback to base R with enhanced error handling
    # Check project data directory first, then fallback to current directory
    stock_file <- file.path(project_data_dir, 'nse_sec_full_data.csv')
    if(!file.exists(stock_file)) {
      stock_file <- 'nse_sec_full_data.csv'
    }
    cat("Loading stock data from:", stock_file, "\n")
    dt_stocks <- read.csv(stock_file, stringsAsFactors = FALSE, fileEncoding = "UTF-8")
    
    # Validate columns
    required_cols <- c("SYMBOL", "TIMESTAMP", "CLOSE", "OPEN", "HIGH", "LOW", "TOTTRDQTY", "TOTTRDVAL")
    missing_cols <- setdiff(required_cols, names(dt_stocks))
    if(length(missing_cols) > 0) {
      stop(paste("Missing required columns:", paste(missing_cols, collapse = ", ")))
    }
    
    dt_stocks$TIMESTAMP <- as.Date(dt_stocks$TIMESTAMP)
    dt_stocks <- dt_stocks[!is.na(dt_stocks$CLOSE) & !is.na(dt_stocks$TIMESTAMP) & dt_stocks$CLOSE > 0 & dt_stocks$TOTTRDVAL > 0, ]
    
    # Remove duplicates - keep the record with highest trading value for each SYMBOL-TIMESTAMP combination
    print(paste("Before deduplication (fallback):", nrow(dt_stocks), "records"))
    dt_stocks <- dt_stocks %>%
      arrange(SYMBOL, TIMESTAMP, desc(TOTTRDVAL)) %>%
      distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE) %>%
      arrange(TIMESTAMP, SYMBOL)
    
    print(paste("After deduplication (fallback):", nrow(dt_stocks), "clean records"))
    
  }, error = function(e2) {
    stop(paste("Failed to load data with both methods:", e2$message))
  })
})

# Load comprehensive NSE index data
print("Loading comprehensive NSE index data...")
tryCatch({
  # Check if index file exists in current directory
  index_file_path <- 'nse_index_data.csv'
  if(!file.exists(index_file_path)) {
    print("Warning: nse_index_data.csv not found in current directory. Relative strength analysis will be skipped.")
    nifty500_data <- NULL
    index_data <- NULL
  } else {
    # Load comprehensive index data
    dt_index <- read.csv(index_file_path, stringsAsFactors = FALSE)
    dt_index$TIMESTAMP <- as.Date(dt_index$TIMESTAMP)
    
    # Store comprehensive index data for analysis
    index_data <- dt_index %>%
      filter(!is.na(CLOSE) & !is.na(TIMESTAMP) & CLOSE > 0) %>%
      arrange(TIMESTAMP)
    
    # Filter for NIFTY500 data for relative strength calculation
    nifty500_data <- dt_index %>%
      filter(grepl("NIFTY 500", SYMBOL, ignore.case = TRUE)) %>%
      arrange(TIMESTAMP)
    
    if(nrow(nifty500_data) == 0) {
      # If NIFTY500 not found, try NIFTY50 as fallback
      nifty500_data <- dt_index %>%
        filter(grepl("NIFTY 50", SYMBOL, ignore.case = TRUE)) %>%
        arrange(TIMESTAMP)
    }
    
    print(paste("Loaded comprehensive index data:", nrow(index_data), "records"))
    print(paste("Loaded NIFTY500 data:", nrow(nifty500_data), "records"))
  }
  
}, error = function(e) {
  print(paste("Error loading index data:", e$message))
  nifty500_data <- NULL
  index_data <- NULL
})

# Load fundamental scores database
print("Loading fundamental scores database...")
fundamental_data <- NULL
tryCatch({
  # Check if fundamental file exists
  if(!file.exists('fundamental_scores_database.csv')) {
    print("Warning: fundamental_scores_database.csv not found. Fundamental analysis will be skipped.")
  } else {
    # Load fundamental scores
    fund_data <- read.csv('fundamental_scores_database.csv', stringsAsFactors = FALSE)
    
    # Clean column names (remove quotes if present)
    colnames(fund_data) <- gsub('"', '', colnames(fund_data))
    
    # Clean and convert symbol to uppercase for matching
    fund_data$symbol <- gsub('"', '', fund_data$symbol)  # Remove quotes
    fund_data$symbol <- toupper(fund_data$symbol)  # Convert to uppercase
    
    # Debug: Check a few symbols
    print(paste("Sample symbols in fundamental data:", head(fund_data$symbol, 5)))
    print(paste("CREDITACC in fundamental data:", "CREDITACC" %in% fund_data$symbol))
    
    print(paste("Loaded fundamental scores data:", nrow(fund_data), "records"))
    fundamental_data <<- fund_data
  }
}, error = function(e) {
  print(paste("Error loading fundamental data:", e$message))
})

# Load company names mapping
print("Loading company names mapping...")
company_names_data <- NULL # Initialize to NULL
tryCatch({
  # Check if company names file exists
  company_names_file <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/data/company_names_mapping.csv'
  if(!file.exists(company_names_file)) {
    print("Warning: company_names_mapping.csv not found. Company names will use symbols.")
  } else {
    # Load company names mapping
    company_data <- read.csv(company_names_file, stringsAsFactors = FALSE)
    
    # Clean column names (remove quotes if present)
    colnames(company_data) <- gsub('"', '', colnames(company_data))
    
    # Clean and convert symbol to uppercase for matching
    company_data$SYMBOL <- gsub('"', '', company_data$SYMBOL)  # Remove quotes
    company_data$SYMBOL <- toupper(company_data$SYMBOL)  # Convert to uppercase
    company_data$COMPANY_NAME <- gsub('"', '', company_data$COMPANY_NAME)  # Remove quotes
    
    # Debug: Check a few symbols
    print(paste("Sample symbols in company names data:", head(company_data$SYMBOL, 5)))
    print(paste("CREDITACC in company names data:", "CREDITACC" %in% company_data$SYMBOL))
    
    print(paste("Loaded company names data:", nrow(company_data), "records"))
    company_names_data <<- company_data # Assign to global environment
  }
}, error = function(e) {
  print(paste("Error loading company names data:", e$message))
})

# Get correct latest date
latest_date <- max(dt_stocks$TIMESTAMP, na.rm = TRUE)
print(paste("Latest data date:", latest_date))

# Get stocks with latest date and apply filtering criteria
latest_stocks <- dt_stocks %>%
  filter(TIMESTAMP == latest_date & !is.na(TOTTRDVAL) & TOTTRDVAL > 0) %>%
  arrange(desc(TOTTRDVAL))

print(paste("Total stocks with data on", latest_date, ":", nrow(latest_stocks)))

# Apply price and volume filtering criteria
filtered_stocks <- latest_stocks %>%
  filter(
    !is.na(CLOSE) & CLOSE > 100 &  # Price above ₹100
    !is.na(TOTTRDQTY) & TOTTRDQTY > 100000  # Volume above 100,000
  ) %>%
  arrange(desc(TOTTRDVAL))

print(paste("Stocks meeting criteria (Price > ₹100 & Volume > 100,000):", nrow(filtered_stocks)))

# Analyze filtered stocks
symbols_to_analyze <- filtered_stocks$SYMBOL

print(paste("Analyzing", length(symbols_to_analyze), "filtered stocks for comprehensive analysis"))

# Function to analyze NSE indices
analyze_nse_indices <- function(index_data, latest_date) {
  # Define major indices to analyze (focused list of indices that exist in data)
  major_indices <- c(
    "Nifty 50",
    "Nifty 100", 
    "Nifty 200",
    "Nifty 500",
    "Nifty Bank",
    "Nifty IT",
    "Nifty Pharma",
    "Nifty Auto",
    "Nifty FMCG",
    "Nifty Metal"
  )
  
  # Function for enhanced technical scoring for indices
  calculate_index_tech_score <- function(index_data, nifty500_data = NULL) {
    if(nrow(index_data) < 50) return(list(score = NA, rsi = NA, trend = NA, momentum = NA, relative_strength = NA))
    
    prices <- index_data$CLOSE
    volumes <- index_data$TOTTRDQTY
    current_price <- tail(prices, 1)
    
    score <- 0
    
    # RSI Score (10 points)
    rsi_val <- tryCatch(tail(RSI(prices, n = 14), 1), error = function(e) NA)
    rsi_score <- 0
    if(!is.na(rsi_val)) {
      if(rsi_val > 40 && rsi_val < 70) rsi_score <- 10
      else if(rsi_val > 30 && rsi_val < 80) rsi_score <- 7
      else rsi_score <- 3
    }
    
    # Enhanced Price Trend Score (25 points)
    trend_score <- 0
    
    # Calculate multiple SMAs
    sma_50 <- tryCatch(tail(SMA(prices, n = 50), 1), error = function(e) NA)
    sma_100 <- tryCatch(tail(SMA(prices, n = 100), 1), error = function(e) NA)
    sma_200 <- tryCatch(tail(SMA(prices, n = 200), 1), error = function(e) NA)
    sma_20 <- tryCatch(tail(SMA(prices, n = 20), 1), error = function(e) NA)
    sma_10 <- tryCatch(tail(SMA(prices, n = 10), 1), error = function(e) NA)
    
    # Price vs SMAs (12 points)
    if(!is.na(sma_200) && current_price > sma_200) trend_score <- trend_score + 3   # Above 200 SMA
    if(!is.na(sma_100) && current_price > sma_100) trend_score <- trend_score + 3   # Above 100 SMA
    if(!is.na(sma_50) && current_price > sma_50) trend_score <- trend_score + 3     # Above 50 SMA
    if(!is.na(sma_20) && current_price > sma_20) trend_score <- trend_score + 2     # Above 20 SMA
    if(!is.na(sma_10) && current_price > sma_10) trend_score <- trend_score + 1     # Above 10 SMA
    
    # SMA Crossovers (13 points)
    if(!is.na(sma_10) && !is.na(sma_20) && sma_10 > sma_20) trend_score <- trend_score + 3    # 10>20 crossover
    if(!is.na(sma_20) && !is.na(sma_50) && sma_20 > sma_50) trend_score <- trend_score + 3    # 20>50 crossover
    if(!is.na(sma_50) && !is.na(sma_100) && sma_50 > sma_100) trend_score <- trend_score + 4  # 50>100 crossover
    if(!is.na(sma_100) && !is.na(sma_200) && sma_100 > sma_200) trend_score <- trend_score + 3 # 100>200 crossover
    
    # Volume Score (15 points)
    volume_score <- 0
    if(length(volumes) >= 10) {
      vol_avg <- mean(tail(volumes, 10), na.rm = TRUE)
      current_vol <- tail(volumes, 1)
      if(!is.na(vol_avg) && !is.na(current_vol)) {
        if(current_vol > vol_avg * 1.5) volume_score <- 15
        else if(current_vol > vol_avg) volume_score <- 10
        else if(current_vol > vol_avg * 0.8) volume_score <- 5
      }
    }
    
    # Relative Strength Score (20 points) - vs NIFTY500
    relative_strength_score <- 0
    relative_strength <- NA
    
    if(!is.null(nifty500_data) && nrow(nifty500_data) >= 50) {
      # Calculate relative strength (index performance vs NIFTY500 over last 50 days)
      index_return <- (current_price / prices[max(1, length(prices)-50)]) - 1
      nifty500_current <- tail(nifty500_data$CLOSE, 1)
      nifty500_50_days_ago <- nifty500_data$CLOSE[max(1, nrow(nifty500_data)-50)]
      nifty500_return <- (nifty500_current / nifty500_50_days_ago) - 1
      
      relative_strength <- index_return - nifty500_return
      
      if(!is.na(relative_strength)) {
        if(relative_strength > 0.10) relative_strength_score <- 20        # 10%+ outperformance
        else if(relative_strength > 0.07) relative_strength_score <- 18   # 7-10% outperformance
        else if(relative_strength > 0.05) relative_strength_score <- 16   # 5-7% outperformance
        else if(relative_strength > 0.03) relative_strength_score <- 14   # 3-5% outperformance
        else if(relative_strength > 0.01) relative_strength_score <- 12   # 1-3% outperformance
        else if(relative_strength > 0) relative_strength_score <- 10      # 0-1% outperformance
        else if(relative_strength > -0.01) relative_strength_score <- 8   # 0-1% underperformance
        else if(relative_strength > -0.03) relative_strength_score <- 6   # 1-3% underperformance
        else if(relative_strength > -0.05) relative_strength_score <- 4   # 3-5% underperformance
        else if(relative_strength > -0.07) relative_strength_score <- 2   # 5-7% underperformance
        else relative_strength_score <- 0                                # >7% underperformance
      }
    }
    
    # Momentum score (30 points) for indices - Reduced weight due to RS addition
    momentum_score <- 0
    momentum_50d <- NA
    if(length(prices) >= 50) {
      # Calculate 50-day momentum
      momentum_50d <- (current_price / prices[max(1, length(prices)-50)]) - 1
      
      if(!is.na(momentum_50d)) {
        if(momentum_50d > 0.10) momentum_score <- 30        # 10%+ gain
        else if(momentum_50d > 0.07) momentum_score <- 27   # 7-10% gain
        else if(momentum_50d > 0.05) momentum_score <- 24   # 5-7% gain
        else if(momentum_50d > 0.03) momentum_score <- 21   # 3-5% gain
        else if(momentum_50d > 0.01) momentum_score <- 18   # 1-3% gain
        else if(momentum_50d > 0) momentum_score <- 15      # 0-1% gain
        else if(momentum_50d > -0.01) momentum_score <- 12  # 0-1% loss
        else if(momentum_50d > -0.03) momentum_score <- 9   # 1-3% loss
        else if(momentum_50d > -0.05) momentum_score <- 6   # 3-5% loss
        else if(momentum_50d > -0.07) momentum_score <- 3   # 5-7% loss
        else momentum_score <- 0                             # >7% loss
      }
    }
    
    total_score <- rsi_score + trend_score + relative_strength_score + momentum_score + volume_score
    
    # Enhanced trend determination
    trend_signal <- "NEUTRAL"
    bullish_count <- 0
    bearish_count <- 0
    
    # Count bullish/bearish signals
    if(!is.na(sma_10) && !is.na(sma_20) && sma_10 > sma_20) bullish_count <- bullish_count + 1
    if(!is.na(sma_20) && !is.na(sma_50) && sma_20 > sma_50) bullish_count <- bullish_count + 1
    if(!is.na(sma_50) && !is.na(sma_100) && sma_50 > sma_100) bullish_count <- bullish_count + 1
    if(!is.na(sma_100) && !is.na(sma_200) && sma_100 > sma_200) bullish_count <- bullish_count + 1
    
    if(!is.na(sma_10) && !is.na(sma_20) && sma_10 < sma_20) bearish_count <- bearish_count + 1
    if(!is.na(sma_20) && !is.na(sma_50) && sma_20 < sma_50) bearish_count <- bearish_count + 1
    if(!is.na(sma_50) && !is.na(sma_100) && sma_50 < sma_100) bearish_count <- bearish_count + 1
    if(!is.na(sma_100) && !is.na(sma_200) && sma_100 < sma_200) bearish_count <- bearish_count + 1
    
    if(bullish_count >= 3) trend_signal <- "STRONG_BULLISH"
    else if(bullish_count >= 2) trend_signal <- "BULLISH"
    else if(bearish_count >= 3) trend_signal <- "STRONG_BEARISH"
    else if(bearish_count >= 2) trend_signal <- "BEARISH"
    
    return(list(
      score = total_score,
      rsi = rsi_val,
      trend = trend_signal,
      momentum = momentum_50d,
      relative_strength = relative_strength
    ))
  }
  
  # Analyze each index with improved matching
  index_results <- data.frame()
  
  # Get NIFTY500 data for relative strength calculation
  nifty500_data <- index_data %>%
    filter(tolower(SYMBOL) == tolower("Nifty 500")) %>%
    arrange(TIMESTAMP)
  
  for(index_name in major_indices) {
    # Get data for this index with improved matching
    index_data_subset <- data.frame()
    
    # Try exact match first
    index_data_subset <- index_data %>%
      filter(SYMBOL == index_name) %>%
      arrange(TIMESTAMP)
    
    # If no exact match, try case-insensitive match
    if(nrow(index_data_subset) == 0) {
      index_data_subset <- index_data %>%
        filter(tolower(SYMBOL) == tolower(index_name)) %>%
        arrange(TIMESTAMP)
    }
    
    # If still no match, try partial matching with common variations
    if(nrow(index_data_subset) == 0) {
      # Handle common variations
      search_terms <- c(
        index_name,
        gsub(" ", "", index_name),  # Remove spaces
        gsub(" ", "_", index_name), # Replace spaces with underscores
        toupper(index_name),        # All caps
        tolower(index_name)         # All lowercase
      )
      
      for(term in search_terms) {
        index_data_subset <- index_data %>%
          filter(grepl(term, SYMBOL, ignore.case = TRUE)) %>%
          arrange(TIMESTAMP)
        if(nrow(index_data_subset) > 0) break
      }
    }
    
    if(nrow(index_data_subset) >= 50) {
      # Calculate technical score with NIFTY500 data for relative strength
      tech_result <- calculate_index_tech_score(index_data_subset, nifty500_data)
      
      # Get current values
      current_level <- tail(index_data_subset$CLOSE, 1)
      
      # Create result row
      result_row <- data.frame(
        INDEX_NAME = index_name,
        CURRENT_LEVEL = current_level,
        TECHNICAL_SCORE = tech_result$score,
        RSI = tech_result$rsi,
        MOMENTUM_50D = tech_result$momentum,
        RELATIVE_STRENGTH = tech_result$relative_strength,
        TREND_SIGNAL = tech_result$trend,
        stringsAsFactors = FALSE
      )
      
      index_results <- rbind(index_results, result_row)
    }
  }
  
  # Add trading signal based on technical score
  index_results$TRADING_SIGNAL <- case_when(
    index_results$TECHNICAL_SCORE >= 80 ~ "STRONG_BUY",
    index_results$TECHNICAL_SCORE >= 65 ~ "BUY",
    index_results$TECHNICAL_SCORE >= 50 ~ "HOLD",
    index_results$TECHNICAL_SCORE >= 35 ~ "WEAK_HOLD",
    TRUE ~ "SELL"
  )
  
  return(index_results)
}

# Function to generate comprehensive markdown report
generate_markdown_report <- function(results, index_results, latest_date, timestamp, output_dir) {
  # Load index analysis data
  index_file <- paste0(output_dir, "nse_index_technical_analysis_", format(as.Date(latest_date), "%d%m%Y"), "_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".csv")
  
  # Try to find the latest index analysis file
  index_files <- list.files(path = output_dir, pattern = "nse_index_technical_analysis_.*\\.csv", full.names = TRUE)
  if(length(index_files) > 0) {
    # Get the most recent file
    latest_index_file <- index_files[order(file.info(index_files)$mtime, decreasing = TRUE)[1]]
    index_data <- read.csv(latest_index_file, stringsAsFactors = FALSE)
  } else {
    index_data <- NULL
  }
  
  # Calculate market breadth
  total_stocks <- nrow(results)
  strong_buy_count <- sum(results$TRADING_SIGNAL == "STRONG_BUY")
  buy_count <- sum(results$TRADING_SIGNAL == "BUY")
  hold_count <- sum(results$TRADING_SIGNAL == "HOLD")
  weak_hold_count <- sum(results$TRADING_SIGNAL == "WEAK_HOLD")
  sell_count <- sum(results$TRADING_SIGNAL == "SELL")
  
  # Calculate market breadth percentages
  strong_buy_pct <- round((strong_buy_count / total_stocks) * 100, 1)
  buy_pct <- round((buy_count / total_stocks) * 100, 1)
  bullish_pct <- round(((strong_buy_count + buy_count) / total_stocks) * 100, 1)
  bearish_pct <- round((sell_count / total_stocks) * 100, 1)
  
  # Create markdown content
  markdown_content <- paste0(
    "# 📊 NSE Market Analysis Report\n",
    "**Analysis Date:** ", latest_date, " | **Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n",
    
    "## 📈 Executive Summary\n\n",
    "This report provides a comprehensive analysis of the NSE stock universe using enhanced technical scoring methodology that combines traditional indicators with William O'Neil's CAN SLIM and Mark Minervini's technical patterns.\n\n",
    
    "### 📊 Filtering Criteria:\n",
    "- **Price Filter:** Stocks with price > ₹100\n",
    "- **Volume Filter:** Stocks with volume > 100,000 shares\n",
    "- **Purpose:** Focus on liquid, higher-priced stocks for better analysis quality\n\n",
    
    "### 🎯 Key Findings:\n",
    "- **Total Stocks Analyzed:** ", total_stocks, "\n",
    "- **Strong Buy Signals:** ", strong_buy_count, " stocks (", strong_buy_pct, "%)\n",
    "- **Buy Signals:** ", buy_count, " stocks (", buy_pct, "%)\n",
    "- **Bullish Market Breadth:** ", bullish_pct, "%\n",
    "- **Bearish Market Breadth:** ", bearish_pct, "%\n",
    "- **Market Conditions:** ", round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1), " average score\n\n"
  )
  
  # Add indices analysis section at the top
  if(!is.null(index_results) && nrow(index_results) > 0) {
    markdown_content <- paste0(markdown_content,
      "## 🏛️ Market Indices Analysis\n\n",
      "### 📊 Top Indices by Technical Score\n\n",
      "| Rank | Index | Current Level | Technical Score | RSI | 50D Momentum | Trend Signal | Trading Signal |\n",
      "|------|-------|---------------|-----------------|-----|--------------|--------------|----------------|\n"
    )
    
    # Sort indices by technical score
    top_indices <- index_results %>% 
      arrange(desc(TECHNICAL_SCORE)) %>%
      head(10)
    
    for(i in 1:nrow(top_indices)) {
      index <- top_indices[i, ]
      
      # Color coding for technical score
      score_color <- ifelse(index$TECHNICAL_SCORE >= 60, "🟢", 
                           ifelse(index$TECHNICAL_SCORE >= 40, "🟡", 
                                  ifelse(index$TECHNICAL_SCORE >= 20, "🟠", "🔴")))
      
      # Color coding for trading signal
      signal_color <- ifelse(index$TRADING_SIGNAL == "STRONG_BUY", "🟢", 
                            ifelse(index$TRADING_SIGNAL == "BUY", "🟡", 
                                   ifelse(index$TRADING_SIGNAL == "HOLD", "🟠", 
                                          ifelse(index$TRADING_SIGNAL == "WEAK_HOLD", "🟠", "🔴"))))
      
      # Color coding for trend signal
      trend_color <- ifelse(index$TREND_SIGNAL == "STRONG_BULLISH", "🟢", 
                           ifelse(index$TREND_SIGNAL == "BULLISH", "🟡", 
                                  ifelse(index$TREND_SIGNAL == "NEUTRAL", "🟠", "🔴")))
      
      # Format momentum with color
      momentum_text <- ifelse(!is.na(index$MOMENTUM_50D), 
                             paste0(ifelse(index$MOMENTUM_50D >= 0, "🟢 +", "🔴 "), 
                                    round(index$MOMENTUM_50D * 100, 1), "%"), "N/A")
      
      markdown_content <- paste0(markdown_content,
        "| ", i, " | **", index$INDEX_NAME, "** | ", format(index$CURRENT_LEVEL, big.mark=","), " | ", 
        score_color, " **", round(index$TECHNICAL_SCORE, 1), "** | ", round(index$RSI, 1), " | ", 
        momentum_text, " | ", trend_color, index$TREND_SIGNAL, " | ", signal_color, index$TRADING_SIGNAL, " |\n"
      )
    }
    
    # Add index summary statistics
    markdown_content <- paste0(markdown_content, "\n",
      "### 📊 Index Performance Summary\n",
      "- **Total Indices Analyzed:** ", nrow(index_results), "\n",
      "- **Average Technical Score:** ", round(mean(index_results$TECHNICAL_SCORE, na.rm = TRUE), 1), "\n",
      "- **Strong Buy Signals:** ", sum(index_results$TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE), "\n",
      "- **Buy Signals:** ", sum(index_results$TRADING_SIGNAL == "BUY", na.rm = TRUE), "\n",
      "- **Hold Signals:** ", sum(index_results$TRADING_SIGNAL == "HOLD", na.rm = TRUE), "\n",
      "- **Weak Hold Signals:** ", sum(index_results$TRADING_SIGNAL == "WEAK_HOLD", na.rm = TRUE), "\n",
      "- **Sell Signals:** ", sum(index_results$TRADING_SIGNAL == "SELL", na.rm = TRUE), "\n\n"
    )
  }
  
  # Add market breadth section
  markdown_content <- paste0(markdown_content,
    "## 📊 Market Breadth Analysis\n\n",
    "### 🎯 Trading Signal Distribution\n\n",
    "| Signal | Count | Percentage | Status |\n",
    "|--------|-------|------------|--------|\n",
    "| 🟢 **STRONG_BUY** | ", strong_buy_count, " | ", strong_buy_pct, "% | ", ifelse(strong_buy_pct >= 5, "🟢 Strong Bullish", ifelse(strong_buy_pct >= 2, "🟡 Moderate", "🔴 Weak")), " |\n",
    "| 🟡 **BUY** | ", buy_count, " | ", buy_pct, "% | ", ifelse(buy_pct >= 10, "🟢 Strong", ifelse(buy_pct >= 5, "🟡 Moderate", "🔴 Weak")), " |\n",
    "| 🟠 **HOLD** | ", hold_count, " | ", round((hold_count / total_stocks) * 100, 1), "% | Neutral |\n",
    "| 🟠 **WEAK_HOLD** | ", weak_hold_count, " | ", round((weak_hold_count / total_stocks) * 100, 1), "% | Weak Bearish |\n",
    "| 🔴 **SELL** | ", sell_count, " | ", bearish_pct, "% | ", ifelse(bearish_pct >= 60, "🔴 Strong Bearish", ifelse(bearish_pct >= 40, "🟠 Moderate", "🟡 Weak")), " |\n\n",
    
    "### 📈 Market Breadth Summary\n",
    "- **🟢 Bullish Breadth:** ", bullish_pct, "% (", strong_buy_count + buy_count, " stocks)\n",
    "- **🔴 Bearish Breadth:** ", bearish_pct, "% (", sell_count, " stocks)\n",
    "- **🟠 Neutral Breadth:** ", round(((hold_count + weak_hold_count) / total_stocks) * 100, 1), "% (", hold_count + weak_hold_count, " stocks)\n\n",
    
    "### 🎯 Market Sentiment\n"
  )
  
  # Determine overall market sentiment
  if(bullish_pct >= 30) {
    sentiment <- "🟢 **BULLISH** - Strong buying pressure with favorable market breadth"
  } else if(bullish_pct >= 20) {
    sentiment <- "🟡 **NEUTRAL-BULLISH** - Moderate buying interest with mixed signals"
  } else if(bullish_pct >= 10) {
    sentiment <- "🟠 **NEUTRAL** - Balanced market with slight bullish bias"
  } else if(bearish_pct >= 60) {
    sentiment <- "🔴 **BEARISH** - Strong selling pressure with poor market breadth"
  } else {
    sentiment <- "🟠 **NEUTRAL-BEARISH** - Weak buying interest with bearish bias"
  }
  
  markdown_content <- paste0(markdown_content, sentiment, "\n\n")
  
  # Add top stocks section
  markdown_content <- paste0(markdown_content,
    "## 🏆 Top 15 Stocks by Technical Score\n\n",
    "| Rank | Stock | Company Name | Market Cap | Current Price | 1D Change | 1W Change | 1M Change | Technical Score | RSI | Relative Strength | CAN SLIM | Minervini | Fundamental | Trend Signal | Trading Signal |\n",
    "|------|-------|-------------|------------|---------------|-----------|-----------|-----------|-----------------|-----|-------------------|----------|-----------|-------------|--------------|----------------|\n"
  )
  
  # Add top 15 stocks with color coding
  top_15 <- head(results[order(-results$TECHNICAL_SCORE), ], 15)
  for(i in 1:nrow(top_15)) {
    stock <- top_15[i, ]
    
    # Color coding for technical score
    score_color <- ifelse(stock$TECHNICAL_SCORE >= 80, "🟢", 
                         ifelse(stock$TECHNICAL_SCORE >= 65, "🟡", 
                                ifelse(stock$TECHNICAL_SCORE >= 50, "🟠", "🔴")))
    
    # Color coding for trading signal
    signal_color <- ifelse(stock$TRADING_SIGNAL == "STRONG_BUY", "🟢", 
                          ifelse(stock$TRADING_SIGNAL == "BUY", "🟡", 
                                 ifelse(stock$TRADING_SIGNAL == "HOLD", "🟠", "🔴")))
    
    # Color coding for trend signal
    trend_color <- ifelse(stock$TREND_SIGNAL == "STRONG_BULLISH", "🟢", 
                         ifelse(stock$TREND_SIGNAL == "BULLISH", "🟡", 
                                ifelse(stock$TREND_SIGNAL == "NEUTRAL", "🟠", "🔴")))
    
    # Color coding for price changes
    change_1d_color <- ifelse(!is.na(stock$CHANGE_1D), 
                             ifelse(stock$CHANGE_1D >= 0, "🟢", "🔴"), "")
    change_1w_color <- ifelse(!is.na(stock$CHANGE_1W), 
                             ifelse(stock$CHANGE_1W >= 0, "🟢", "🔴"), "")
    change_1m_color <- ifelse(!is.na(stock$CHANGE_1M), 
                             ifelse(stock$CHANGE_1M >= 0, "🟢", "🔴"), "")
    
            # Color coding for fundamental score
        fund_color <- ifelse(!is.na(stock$ENHANCED_FUND_SCORE), 
                           ifelse(stock$ENHANCED_FUND_SCORE >= 70, "🟢", 
                                  ifelse(stock$ENHANCED_FUND_SCORE >= 60, "🟡", 
                                         ifelse(stock$ENHANCED_FUND_SCORE >= 50, "🟠", "🔴"))), "")
        
        markdown_content <- paste0(markdown_content,
          "| ", i, " | **", stock$SYMBOL, "** | ", stock$COMPANY_NAME, " | ", stock$MARKET_CAP_CATEGORY, " | ₹", 
          format(stock$CURRENT_PRICE, big.mark=","), " | ", 
          change_1d_color, ifelse(!is.na(stock$CHANGE_1D), paste0(ifelse(stock$CHANGE_1D >= 0, "+", ""), round(stock$CHANGE_1D, 2), "%"), "N/A"), " | ",
          change_1w_color, ifelse(!is.na(stock$CHANGE_1W), paste0(ifelse(stock$CHANGE_1W >= 0, "+", ""), round(stock$CHANGE_1W, 2), "%"), "N/A"), " | ",
          change_1m_color, ifelse(!is.na(stock$CHANGE_1M), paste0(ifelse(stock$CHANGE_1M >= 0, "+", ""), round(stock$CHANGE_1M, 2), "%"), "N/A"), " | ",
          score_color, " **", stock$TECHNICAL_SCORE, "** | ", round(stock$RSI, 1), " | ", 
          ifelse(!is.na(stock$RELATIVE_STRENGTH), paste0(ifelse(stock$RELATIVE_STRENGTH >= 0, "+", ""), round(stock$RELATIVE_STRENGTH, 2), "%"), "N/A"), " | ",
          stock$CAN_SLIM_SCORE, " | ", stock$MINERVINI_SCORE, " | ", fund_color, ifelse(!is.na(stock$ENHANCED_FUND_SCORE), round(stock$ENHANCED_FUND_SCORE, 1), "N/A"), " | ", trend_color, stock$TREND_SIGNAL, " | ", signal_color, stock$TRADING_SIGNAL, " |\n"
        )
  }
  
  # Add market cap category analysis with consistent formatting
  markdown_content <- paste0(markdown_content, "\n\n## 📊 TOP PERFORMERS BY MARKET CAP CATEGORY\n\n")
  
  cap_icons <- c("LARGE_CAP" = "🏢", "MID_CAP" = "🏭", "SMALL_CAP" = "🏪", "MICRO_CAP" = "🔬")
  
  for(cap_category in c("LARGE_CAP", "MID_CAP", "SMALL_CAP", "MICRO_CAP")) {
    cap_stocks <- results[results$MARKET_CAP_CATEGORY == cap_category, ]
    if(nrow(cap_stocks) > 0) {
      top_5_cap <- head(cap_stocks[order(-cap_stocks$TECHNICAL_SCORE), ], 5)
      
      markdown_content <- paste0(markdown_content,
        cap_icons[cap_category], " **", cap_category, " - TOP 5**\n",
        "| Rank | Stock | Company Name | Current Price | Technical Score | Relative Strength | CAN SLIM | Minervini | Fundamental | Trend Signal | Trading Signal |\n",
        "|------|-------|-------------|---------------|-----------------|-------------------|----------|-----------|-------------|--------------|----------------|\n"
      )
      
      for(j in 1:nrow(top_5_cap)) {
        stock <- top_5_cap[j, ]
        
        # Color coding for technical score
        score_color <- ifelse(stock$TECHNICAL_SCORE >= 80, "🟢", 
                             ifelse(stock$TECHNICAL_SCORE >= 65, "🟡", 
                                    ifelse(stock$TECHNICAL_SCORE >= 50, "🟠", "🔴")))
        
        # Color coding for trading signal
        signal_color <- ifelse(stock$TRADING_SIGNAL == "STRONG_BUY", "🟢", 
                              ifelse(stock$TRADING_SIGNAL == "BUY", "🟡", 
                                     ifelse(stock$TRADING_SIGNAL == "HOLD", "🟠", "🔴")))
        
        # Color coding for trend signal
        trend_color <- ifelse(stock$TREND_SIGNAL == "STRONG_BULLISH", "🟢", 
                             ifelse(stock$TREND_SIGNAL == "BULLISH", "🟡", 
                                    ifelse(stock$TREND_SIGNAL == "NEUTRAL", "🟠", "🔴")))
        
        # Color coding for fundamental score
        fund_color <- ifelse(!is.na(stock$ENHANCED_FUND_SCORE), 
                           ifelse(stock$ENHANCED_FUND_SCORE >= 70, "🟢", 
                                  ifelse(stock$ENHANCED_FUND_SCORE >= 60, "🟡", 
                                         ifelse(stock$ENHANCED_FUND_SCORE >= 50, "🟠", "🔴"))), "")
        
        markdown_content <- paste0(markdown_content,
          "| ", j, " | **", stock$SYMBOL, "** | ", stock$COMPANY_NAME, " | ₹", format(stock$CURRENT_PRICE, big.mark=","), " | ", 
          score_color, " **", stock$TECHNICAL_SCORE, "** | ", 
          ifelse(!is.na(stock$RELATIVE_STRENGTH), paste0(ifelse(stock$RELATIVE_STRENGTH >= 0, "+", ""), round(stock$RELATIVE_STRENGTH, 2), "%"), "N/A"), " | ",
          stock$CAN_SLIM_SCORE, " | ", stock$MINERVINI_SCORE, " | ", fund_color, ifelse(!is.na(stock$ENHANCED_FUND_SCORE), round(stock$ENHANCED_FUND_SCORE, 1), "N/A"), " | ", trend_color, stock$TREND_SIGNAL, " | ", signal_color, stock$TRADING_SIGNAL, " |\n"
        )
      }
      markdown_content <- paste0(markdown_content, "\n")
    }
  }
  
  # Add color legend
  markdown_content <- paste0(markdown_content,
    "## 🎨 Color Coding Legend\n\n",
    "### 📈 Performance Indicators:\n",
    "- 🟢 **Green:** Excellent performance (Score ≥80, Strong Buy, Strong Bullish, Positive changes)\n",
    "- 🟡 **Yellow:** Good performance (Score 65-79, Buy, Bullish)\n",
    "- 🟠 **Orange:** Moderate performance (Score 50-64, Hold, Neutral)\n",
    "- 🔴 **Red:** Poor performance (Score <50, Sell, Bearish, Negative changes)\n\n",
    
    "### 📊 Technical Score Ranges:\n",
    "- 🟢 **80-100:** STRONG_BUY signals\n",
    "- 🟡 **65-79:** BUY signals\n",
    "- 🟠 **50-64:** HOLD signals\n",
    "- 🔴 **<50:** SELL/WEAK_HOLD signals\n\n"
  )
  
  # Add trading signals summary
  signal_summary <- table(results$TRADING_SIGNAL)
  markdown_content <- paste0(markdown_content,
    "## 📊 Trading Signals Summary\n\n",
    "| Signal | Count | Percentage |\n",
    "|--------|-------|------------|\n"
  )
  
  for(signal in names(signal_summary)) {
    count <- signal_summary[signal]
    percentage <- round((count / nrow(results)) * 100, 1)
    markdown_content <- paste0(markdown_content,
      "| ", signal, " | ", count, " | ", percentage, "% |\n"
    )
  }
  
  # Add methodology explanation
  markdown_content <- paste0(markdown_content,
    "\n## 🔧 Technical Scoring Methodology\n\n",
    "### **📊 Enhanced Technical Scoring Formula (0-100 scale) - With Equal Weight Minervini & Relative Strength**\n\n",
    "| Component | Points | Description |\n",
    "|-----------|--------|-------------|\n",
    "| **RSI Score** | 8 | Optimal range 40-70 |\n",
    "| **Price vs SMAs** | 10 | Above 10,20,50,100,200 SMAs |\n",
    "| **SMA Crossovers** | 10 | 10>20, 20>50, 50>100, 100>200 |\n",
    "| **Relative Strength** | 20 | vs NIFTY500 over 50 days - **EQUAL WEIGHT WITH MINERVINI** |\n",
    "| **Volume Score** | 12 | vs 10-day average |\n",
    "| **CAN SLIM Score** | 20 | William O'Neil methodology |\n",
    "| **Minervini Score** | 20 | Mark Minervini methodology - **EQUAL WEIGHT WITH RELATIVE STRENGTH** |\n\n",
    
    "### **📈 Trading Signal Classification**\n",
    "- **STRONG_BUY:** Score ≥ 80\n",
    "- **BUY:** Score ≥ 65\n", 
    "- **HOLD:** Score ≥ 50\n",
    "- **WEAK_HOLD:** Score ≥ 35\n",
    "- **SELL:** Score < 35\n\n",
    
    "## 🎯 Investment Recommendations\n\n",
    "### **🥇 Top Priority Picks (CAN SLIM + Minervini Approved):**\n"
  )
  
  # Add top recommendations
  strong_buys <- results[results$TRADING_SIGNAL == "STRONG_BUY", ]
  if(nrow(strong_buys) > 0) {
    top_recommendations <- head(strong_buys[order(-strong_buys$TECHNICAL_SCORE), ], 5)
    for(k in 1:nrow(top_recommendations)) {
      stock <- top_recommendations[k, ]
      markdown_content <- paste0(markdown_content,
        k, ". **", stock$SYMBOL, "** - Score: ", stock$TECHNICAL_SCORE, 
        ", CAN SLIM: ", stock$CAN_SLIM_SCORE, "/20, Minervini: ", stock$MINERVINI_SCORE, "/20\n"
      )
    }
  }
  
  # Add footer
  markdown_content <- paste0(markdown_content,
    "\n---\n",
    "**Report Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n",
    "**Data Source:** NSE Historical Data\n",
    "**Analysis Method:** Enhanced Technical Scoring with CAN SLIM & Minervini Indicators\n"
  )
  
  # Save markdown file
  markdown_filename <- paste0(output_dir, "NSE_Analysis_Report_", format(latest_date, "%Y%m%d"), "_", timestamp, ".md")
  writeLines(markdown_content, markdown_filename)
  
  cat("Markdown report saved to:", markdown_filename, "\n")
}

# Function to generate HTML dashboard
generate_html_dashboard <- function(results, index_results, latest_date, timestamp, output_dir) {
  # Get all stocks for the dashboard (sorted by technical score)
  top_50_stocks <- results[order(-results$TECHNICAL_SCORE), ]
  
  # Enhanced dashboard with charting functionality
  cat("Generating enhanced dashboard with charting functionality...\n")
  
  # Create JavaScript data array
  js_data <- ""
  for(i in 1:nrow(top_50_stocks)) {
    stock <- top_50_stocks[i, ]
    js_data <- paste0(js_data, 
      "            {\n",
      "                rank: ", i, ",\n",
      "                symbol: \"", gsub('"', '\\\\"', stock$SYMBOL), "\",\n",
      "                companyName: \"", gsub('"', '\\\\"', gsub("'", "\\\\'", ifelse(is.na(stock$COMPANY_NAME) || stock$COMPANY_NAME == "", stock$SYMBOL, stock$COMPANY_NAME))), "\",\n",
      "                marketCap: \"", stock$MARKET_CAP_CATEGORY, "\",\n",
      "                currentPrice: ", stock$CURRENT_PRICE, ",\n",
      "                change1D: ", ifelse(is.na(stock$CHANGE_1D), 0, stock$CHANGE_1D), ",\n",
      "                change1W: ", ifelse(is.na(stock$CHANGE_1W), 0, stock$CHANGE_1W), ",\n",
      "                change1M: ", ifelse(is.na(stock$CHANGE_1M), 0, stock$CHANGE_1M), ",\n",
      "                technicalScore: ", stock$TECHNICAL_SCORE, ",\n",
      "                rsi: ", stock$RSI, ",\n",
      "                relativeStrength: ", ifelse(is.na(stock$RELATIVE_STRENGTH), 0, stock$RELATIVE_STRENGTH), ",\n",
      "                canSlim: ", stock$CAN_SLIM_SCORE, ",\n",
      "                minervini: ", stock$MINERVINI_SCORE, ",\n",
      "                fundamental: ", ifelse(is.na(stock$ENHANCED_FUND_SCORE), 0, stock$ENHANCED_FUND_SCORE), ",\n",
      "                trendSignal: \"", stock$TREND_SIGNAL, "\",\n",
      "                tradingSignal: \"", stock$TRADING_SIGNAL, "\"\n",
      "            }")
    
    if(i < nrow(top_50_stocks)) {
      js_data <- paste0(js_data, ",\n")
    }
  }
  
  
  # Create HTML content using a simpler approach
  html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Market Analysis Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: "Roboto", "Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #212121;
            font-weight: 400;
            line-height: 1.6;
        }

        .container {
            max-width: 100%;
            margin: 0 auto;
            padding: 20px;
            width: 100%;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
            color: white;
        }

        .header h1 {
            font-size: 3rem;
            font-weight: 300;
            margin-bottom: 16px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
            letter-spacing: -0.5px;
        }

        .header p {
            font-size: 1.25rem;
            font-weight: 400;
            opacity: 0.95;
            letter-spacing: 0.2px;
        }

        .header .date-display {
            font-size: 1rem;
            font-weight: 500;
            margin-top: 12px;
            opacity: 0.9;
            background: rgba(255, 255, 255, 0.15);
            padding: 8px 20px;
            border-radius: 20px;
            display: inline-block;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px 24px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            text-align: center;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .stat-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0,0,0,0.2);
        }

        .stat-number {
            font-size: 3rem;
            font-weight: 300;
            color: #1976d2;
            margin-bottom: 12px;
            line-height: 1;
        }

        .stat-label {
            color: #616161;
            font-size: 0.875rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }

        .chart-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .chart-title {
            font-size: 1.5rem;
            font-weight: 500;
            margin-bottom: 24px;
            color: #1976d2;
            text-align: center;
            letter-spacing: 0.2px;
        }

        .index-analysis-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            margin-bottom: 32px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .index-title {
            font-size: 1.5rem;
            font-weight: 500;
            margin-bottom: 24px;
            color: #1976d2;
            text-align: center;
            letter-spacing: 0.2px;
        }

        .index-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
        }

        .index-card {
            background: rgba(255, 255, 255, 0.8);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(0,0,0,0.05);
        }

        .index-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.15);
        }

        .index-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .index-name {
            font-size: 1.1rem;
            font-weight: 600;
            color: #212121;
        }

        .index-score {
            font-size: 1.5rem;
            font-weight: 700;
            padding: 8px 12px;
            border-radius: 8px;
            background: rgba(0,0,0,0.05);
        }

        .index-details {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .index-level {
            font-size: 1.25rem;
            font-weight: 600;
            color: #1976d2;
        }

        .index-metrics {
            display: flex;
            gap: 16px;
            font-size: 0.9rem;
        }

        .metric {
            padding: 4px 8px;
            background: rgba(0,0,0,0.05);
            border-radius: 4px;
            font-weight: 500;
        }

        .index-signals {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .signal {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
            color: white;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .trend {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
            background: rgba(0,0,0,0.1);
            color: #616161;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .heatmap-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            margin-bottom: 32px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .heatmap-title {
            font-size: 1.5rem;
            font-weight: 500;
            margin-bottom: 24px;
            color: #1976d2;
            text-align: center;
            letter-spacing: 0.2px;
        }

        .heatmap-grid {
            display: grid;
            grid-template-columns: repeat(10, 1fr);
            gap: 3px;
            margin-bottom: 20px;
        }

        .heatmap-cell {
            aspect-ratio: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            font-weight: 600;
            color: white;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            min-width: 40px;
            min-height: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .heatmap-cell:hover {
            transform: scale(1.15);
            z-index: 10;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        }

        .heatmap-cell.excellent { background: linear-gradient(135deg, #4CAF50, #66BB6A); }
        .heatmap-cell.good { background: linear-gradient(135deg, #8BC34A, #9CCC65); }
        .heatmap-cell.moderate { background: linear-gradient(135deg, #FFC107, #FFD54F); }
        .heatmap-cell.poor { background: linear-gradient(135deg, #FF9800, #FFB74D); }
        .heatmap-cell.very-poor { background: linear-gradient(135deg, #F44336, #EF5350); }

        .heatmap-legend {
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9rem;
        }

        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 3px;
        }

        .breadth-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }

        .breadth-card {
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            color: white;
            font-weight: 600;
            box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .breadth-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }

        .breadth-card.bullish { background: linear-gradient(135deg, #4CAF50, #66BB6A); }
        .breadth-card.neutral { background: linear-gradient(135deg, #FFC107, #FFD54F); }
        .breadth-card.bearish { background: linear-gradient(135deg, #F44336, #EF5350); }

        .stocks-table-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
            overflow-x: auto;
            max-width: 100%;
            position: relative;
        }
        
        .stocks-table-container::before {
            content: "← Scroll horizontally to see all columns →";
            position: absolute;
            top: 10px;
            right: 20px;
            background: rgba(25, 118, 210, 0.1);
            color: #1976d2;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.75rem;
            font-weight: 500;
            z-index: 10;
        }

        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .table-title {
            font-size: 1.5rem;
            font-weight: 500;
            color: #1976d2;
            letter-spacing: 0.2px;
        }

        .filters {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 10px 20px;
            border: 2px solid #1976d2;
            background: rgba(255, 255, 255, 0.9);
            color: #1976d2;
            border-radius: 24px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 0.875rem;
            font-weight: 500;
            letter-spacing: 0.5px;
        }

        .filter-btn.active,
        .filter-btn:hover {
            background: #1976d2;
            color: white;
            box-shadow: 0 4px 12px rgba(25, 118, 210, 0.3);
            transform: translateY(-2px);
        }

        .search-box {
            padding: 12px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 24px;
            font-size: 0.875rem;
            outline: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            background: rgba(255, 255, 255, 0.9);
        }

        .search-box:focus {
            border-color: #1976d2;
            box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.1);
            background: white;
        }

        .stocks-table {
            width: 100%;
            min-width: 1200px;
            border-collapse: collapse;
            font-size: 0.9rem;
        }

        .stocks-table th {
            background: #f5f5f5;
            padding: 16px 12px;
            text-align: left;
            font-weight: 600;
            color: #1976d2;
            border-bottom: 2px solid #e0e0e0;
            font-size: 0.875rem;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
            transition: background-color 0.2s ease;
            position: relative;
        }

        .stocks-table th:hover {
            background: #e3f2fd;
        }

        .stocks-table th.sortable {
            position: relative;
        }

        .stocks-table th.sort-asc {
            background: #e8f5e8;
        }

        .stocks-table th.sort-desc {
            background: #ffe8e8;
        }

        .stocks-table td {
            padding: 12px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 0.875rem;
        }

        .stocks-table tr:hover {
            background: rgba(25, 118, 210, 0.04);
            transition: background 0.2s ease;
        }

        .signal-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .signal-strong-buy { background: linear-gradient(135deg, #4CAF50, #66BB6A); color: white; }
        .signal-buy { background: linear-gradient(135deg, #8BC34A, #9CCC65); color: white; }
        .signal-hold { background: linear-gradient(135deg, #FFC107, #FFD54F); color: #333; }
        .signal-weak-hold { background: linear-gradient(135deg, #FF9800, #FFB74D); color: white; }
        .signal-sell { background: linear-gradient(135deg, #F44336, #EF5350); color: white; }

        .trend-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .trend-strong-bullish { background: linear-gradient(135deg, #4CAF50, #66BB6A); color: white; }
        .trend-bullish { background: linear-gradient(135deg, #8BC34A, #9CCC65); color: white; }
        .trend-neutral { background: linear-gradient(135deg, #FFC107, #FFD54F); color: #333; }
        .trend-bearish { background: linear-gradient(135deg, #FF9800, #FFB74D); color: white; }
        .trend-strong-bearish { background: linear-gradient(135deg, #F44336, #EF5350); color: white; }

        .market-cap-badge {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .market-cap-large_cap { background: linear-gradient(135deg, #2196F3, #42A5F5); color: white; }
        .market-cap-mid_cap { background: linear-gradient(135deg, #9C27B0, #BA68C8); color: white; }
        .market-cap-small_cap { background: linear-gradient(135deg, #FF5722, #FF7043); color: white; }
        .market-cap-micro_cap { background: linear-gradient(135deg, #607D8B, #90A4AE); color: white; }

        .positive { color: #2E7D32; font-weight: 600; }
        .negative { color: #D32F2F; font-weight: 600; }
        
        /* Chart Styles */
        .chart-section {
            margin-top: 1rem;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }
        
        .chart-controls {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }
        
        .chart-btn {
            padding: 0.5rem 1rem;
            border: 1px solid #dee2e6;
            background: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.875rem;
            transition: all 0.2s ease;
        }
        
        .chart-btn:hover {
            background: #e9ecef;
        }
        
        .chart-btn.active {
            background: #1976d2;
            color: white;
            border-color: #1976d2;
        }
        
        .chart-wrapper {
            position: relative;
            height: 300px;
            margin-bottom: 1rem;
        }
        
        .volume-chart-wrapper {
            position: relative;
            height: 100px;
        }
        
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 200px;
            color: #666;
            font-size: 1rem;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #1976d2;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            backdrop-filter: blur(5px);
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal-content {
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(20px);
            border-radius: 20px;
            padding: 2.5rem;
            max-width: 550px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.25);
            transform: scale(0.7);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .modal-overlay.active .modal-content {
            transform: scale(1);
            opacity: 1;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid #f0f0f0;
        }

        .modal-title {
            font-size: 1.75rem;
            font-weight: 500;
            color: #1976d2;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            letter-spacing: 0.2px;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #666;
            padding: 0.5rem;
            border-radius: 50%;
            transition: all 0.2s ease;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-close:hover {
            background: #f0f0f0;
            color: #333;
        }

        .stock-details {
            display: grid;
            gap: 1rem;
        }

        .detail-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            padding: 1.5rem;
            background: rgba(25, 118, 210, 0.04);
            border-radius: 12px;
            border-left: 4px solid #1976d2;
            transition: all 0.2s ease;
        }

        .detail-row:hover {
            background: rgba(25, 118, 210, 0.08);
            transform: translateX(4px);
        }

        .detail-item {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .detail-label {
            font-size: 0.75rem;
            color: #616161;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 500;
        }

        .detail-value {
            font-size: 1.125rem;
            font-weight: 600;
            color: #212121;
        }

        .detail-value.positive { color: #4CAF50; }
        .detail-value.negative { color: #F44336; }

        .signal-badge-modal {
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: bold;
            text-align: center;
            display: inline-block;
        }

        .signal-strong-buy-modal { background: #4CAF50; color: white; }
        .signal-buy-modal { background: #8BC34A; color: white; }
        .signal-hold-modal { background: #FFC107; color: #333; }
        .signal-weak-hold-modal { background: #FF9800; color: white; }
        .signal-sell-modal { background: #F44336; color: white; }

        .trend-badge-modal {
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: bold;
            text-align: center;
            display: inline-block;
        }

        .trend-strong-bullish-modal { background: #4CAF50; color: white; }
        .trend-bullish-modal { background: #8BC34A; color: white; }
        .trend-neutral-modal { background: #FFC107; color: #333; }
        .trend-bearish-modal { background: #FF9800; color: white; }
        .trend-strong-bearish-modal { background: #F44336; color: white; }

        .market-cap-badge-modal {
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: bold;
            text-align: center;
            display: inline-block;
        }

        .market-cap-large_cap-modal { background: #2196F3; color: white; }
        .market-cap-mid_cap-modal { background: #9C27B0; color: white; }
        .market-cap-small_cap-modal { background: #FF5722; color: white; }
        .market-cap-micro_cap-modal { background: #607D8B; color: white; }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
            
            .heatmap-grid {
                grid-template-columns: repeat(10, 1fr);
                font-size: 0.5rem;
            }
            
            .heatmap-cell {
                min-width: 30px;
                min-height: 30px;
                font-size: 0.5rem;
            }
            
            .heatmap-legend {
                flex-direction: column;
                align-items: center;
            }
            
            .breadth-summary {
                grid-template-columns: 1fr;
            }
            
            .table-header {
                flex-direction: column;
                align-items: stretch;
                gap: 15px;
            }
            
            .filters {
                justify-content: center;
                flex-wrap: wrap;
            }
            
            .stocks-table-container {
                padding: 16px;
                overflow-x: auto;
            }
            
            .stocks-table {
                min-width: 1000px;
                font-size: 0.8rem;
            }
            
            .stocks-table th,
            .stocks-table td {
                padding: 8px 6px;
            }
        }

        @media (max-width: 480px) {
            .heatmap-grid {
                grid-template-columns: repeat(10, 1fr);
                font-size: 0.4rem;
            }
            
            .heatmap-cell {
                min-width: 25px;
                min-height: 25px;
                font-size: 0.4rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NSE Market Analysis Dashboard</h1>
            <p>Comprehensive Technical Analysis with CAN SLIM & Minervini Indicators</p>
            <div class="date-display">📅 Data as of: ', format(latest_date, "%B %d, %Y"), '</div>
        </div>

        <!-- Index Analysis Section -->
        <div class="index-analysis-container">
            <div class="index-title">🏛️ NSE Indices Analysis</div>
            <div class="index-grid">
'
  )
  
  # Add index analysis data
  if(!is.null(index_results) && nrow(index_results) > 0) {
    # Sort indices by technical score
    top_indices <- index_results %>% 
      arrange(desc(TECHNICAL_SCORE)) %>%
      head(10)
    
    # Use the actual index analysis results from analyze_nse_indices function
    # The index_results already contains real analysis data - no need for hardcoded values
    
    for(i in 1:nrow(top_indices)) {
      index <- top_indices[i, ]
      
      # Color coding for technical score
      score_color <- ifelse(index$TECHNICAL_SCORE >= 60, "#4CAF50", 
                           ifelse(index$TECHNICAL_SCORE >= 40, "#8BC34A", 
                                  ifelse(index$TECHNICAL_SCORE >= 20, "#FFC107", "#F44336")))
      
      # Color coding for trading signal
      signal_color <- ifelse(index$TRADING_SIGNAL == "STRONG_BUY", "#4CAF50", 
                            ifelse(index$TRADING_SIGNAL == "BUY", "#8BC34A", 
                                   ifelse(index$TRADING_SIGNAL == "HOLD", "#FFC107", 
                                          ifelse(index$TRADING_SIGNAL == "WEAK_HOLD", "#FF9800", "#F44336"))))
      
      # Format momentum with color
      momentum_text <- ifelse(!is.na(index$MOMENTUM_50D), 
                             paste0(ifelse(index$MOMENTUM_50D >= 0, "+", ""), 
                                    round(index$MOMENTUM_50D * 100, 1), "%"), "N/A")
      momentum_color <- ifelse(!is.na(index$MOMENTUM_50D) && index$MOMENTUM_50D >= 0, "#4CAF50", "#F44336")
      
      # Format relative strength with color
      rs_text <- ifelse(!is.na(index$RELATIVE_STRENGTH), 
                       paste0(ifelse(index$RELATIVE_STRENGTH >= 0, "+", ""), 
                              round(index$RELATIVE_STRENGTH * 100, 1), "%"), "N/A")
      rs_color <- ifelse(!is.na(index$RELATIVE_STRENGTH) && index$RELATIVE_STRENGTH >= 0, "#4CAF50", "#F44336")
      
      html_content <- paste0(html_content,
        '                <div class="index-card">
                    <div class="index-header">
                        <div class="index-name">', index$INDEX_NAME, '</div>
                        <div class="index-score" style="color: ', score_color, ';">', round(index$TECHNICAL_SCORE, 1), '</div>
                    </div>
                    <div class="index-details">
                        <div class="index-level">₹', format(index$CURRENT_LEVEL, big.mark=","), '</div>
                        <div class="index-metrics">
                            <span class="metric">RSI: ', round(index$RSI, 1), '</span>
                            <span class="metric" style="color: ', momentum_color, ';">50D: ', momentum_text, '</span>
                            <span class="metric" style="color: ', rs_color, ';">RS: ', rs_text, '</span>
                        </div>
                        <div class="index-signals">
                            <span class="signal" style="background: ', signal_color, ';">', index$TRADING_SIGNAL, '</span>
                            <span class="trend">', index$TREND_SIGNAL, '</span>
                        </div>
                    </div>
                </div>
                ')
    }
  }
  
  html_content <- paste0(html_content,
        '            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">', nrow(results), '</div>
                <div class="stat-label">Total Stocks Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(results$TRADING_SIGNAL == "STRONG_BUY"), '</div>
                <div class="stat-label">Strong Buy Signals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(results$TRADING_SIGNAL == "BUY"), '</div>
                <div class="stat-label">Buy Signals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1), '</div>
                <div class="stat-label">Average Technical Score</div>
            </div>
        </div>
        ')

  html_content <- paste0(html_content,
        '<div class="heatmap-container">
            <div class="heatmap-title">🔥 Market Breadth Heat Map</div>
            <div id="breadthHeatmap" class="heatmap-grid"></div>
            <div class="heatmap-legend">
                <div class="legend-item">
                    <div class="legend-color" style="background: #4CAF50;"></div>
                    <span>Excellent (80+)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #8BC34A;"></div>
                    <span>Good (65-79)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #FFC107;"></div>
                    <span>Moderate (50-64)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #FF9800;"></div>
                    <span>Poor (35-49)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #F44336;"></div>
                    <span>Very Poor (<35)</span>
                </div>
            </div>
            <div class="breadth-summary">
                <div class="breadth-card bullish">
                    <div style="font-size: 1.5rem;">', sum(results$TRADING_SIGNAL %in% c("STRONG_BUY", "BUY")), '</div>
                    <div>Bullish Stocks</div>
                </div>
                <div class="breadth-card neutral">
                    <div style="font-size: 1.5rem;">', sum(results$TRADING_SIGNAL == "HOLD"), '</div>
                    <div>Neutral Stocks</div>
                </div>
                <div class="breadth-card bearish">
                    <div style="font-size: 1.5rem;">', sum(results$TRADING_SIGNAL %in% c("WEAK_HOLD", "SELL")), '</div>
                    <div>Bearish Stocks</div>
                </div>
            </div>
        </div>

        <div class="stocks-table-container">
            <div class="table-header">
                <div class="table-title">📋 Top 50 Stocks Analysis</div>
                <div class="filters">
                    <input type="text" id="stockSearch" class="search-box" placeholder="Search stocks...">
                    <button class="filter-btn active" data-filter="all">All</button>
                    <button class="filter-btn" data-filter="strong-buy">Strong Buy</button>
                    <button class="filter-btn" data-filter="buy">Buy</button>
                    <button class="filter-btn" data-filter="large-cap">Large Cap</button>
                    <button class="filter-btn" data-filter="mid-cap">Mid Cap</button>
                    <button class="filter-btn" data-filter="small-cap">Small Cap</button>
                    <button class="filter-btn" data-filter="micro-cap">Micro Cap</button>
                </div>
            </div>
            <table class="stocks-table" id="stocksTable">
                <thead>
                    <tr>
                        <th class="sortable" data-sort="rank">Rank</th>
                        <th class="sortable" data-sort="symbol">Stock</th>
                        <th class="sortable" data-sort="companyName">Company Name</th>
                        <th class="sortable" data-sort="marketCap">Market Cap</th>
                        <th class="sortable" data-sort="currentPrice">Price</th>
                        <th class="sortable" data-sort="change1D">1D</th>
                        <th class="sortable" data-sort="change1W">1W</th>
                        <th class="sortable" data-sort="change1M">1M</th>
                        <th class="sortable" data-sort="technicalScore">Tech Score</th>
                        <th class="sortable" data-sort="rsi">RSI</th>
                        <th class="sortable" data-sort="relativeStrength">RS</th>
                        <th class="sortable" data-sort="canSlim">CAN SLIM</th>
                        <th class="sortable" data-sort="minervini">Minervini</th>
                        <th class="sortable" data-sort="fundamental">Fundamental</th>
                        <th class="sortable" data-sort="trendSignal">Trend</th>
                        <th class="sortable" data-sort="tradingSignal">Signal</th>
                    </tr>
                </thead>
                <tbody id="stocksTableBody">
                </tbody>
            </table>
        </div>
    </div>

    <!-- Modal for stock details -->
    <div class="modal-overlay" id="stockModal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalStockSymbol"></div>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="stock-details" id="modalStockDetails">
            </div>
            
            <!-- Chart Section -->
            <div class="chart-section">
                <div class="chart-controls">
                    <button class="chart-btn active" data-period="1M">1M</button>
                    <button class="chart-btn" data-period="3M">3M</button>
                    <button class="chart-btn" data-period="6M">6M</button>
                    <button class="chart-btn" data-period="1Y">1Y</button>
                    <button class="chart-btn" data-period="ALL">ALL</button>
                </div>
                <div class="chart-wrapper">
                    <div class="loading" id="chartLoading">
                        <div class="spinner"></div>
                        Loading chart data...
                    </div>
                    <canvas id="stockChart" style="display: none;"></canvas>
                </div>
                <div class="volume-chart-wrapper">
                    <canvas id="volumeChart" style="display: none;"></canvas>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Stock data from analysis
        const stocksData = [
', js_data, '
        ];


        // Initialize charts (removed Trading Signal and Market Cap charts)
        function initializeCharts() {
            // Charts removed as requested
        }

        // Global variables for sorting
        let currentSortColumn = null;
        let currentSortDirection = "asc";

        // Populate stocks table
        function populateStocksTable(data = stocksData) {
            console.log("populateStocksTable called with", data ? data.length : 0, "items");
            const tbody = document.getElementById("stocksTableBody");
            if (!tbody) {
                console.error("stocksTableBody element not found!");
                return;
            }
            console.log("Table body found, clearing...");
            tbody.innerHTML = "";

            data.forEach(function(stock, index) {
                const row = document.createElement("tr");
                const change1DClass = stock.change1D >= 0 ? "positive" : "negative";
                const change1WClass = stock.change1W >= 0 ? "positive" : "negative";
                const change1MClass = stock.change1M >= 0 ? "positive" : "negative";
                const rsClass = stock.relativeStrength >= 0 ? "positive" : "negative";
                const change1DSign = stock.change1D >= 0 ? "+" : "";
                const change1WSign = stock.change1W >= 0 ? "+" : "";
                const change1MSign = stock.change1M >= 0 ? "+" : "";
                const rsSign = stock.relativeStrength >= 0 ? "+" : "";
                const marketCapLower = stock.marketCap.toLowerCase();
                const marketCapDisplay = stock.marketCap.replace("_", " ");
                const trendSignalLower = stock.trendSignal.toLowerCase().replace("_", "-");
                const trendSignalDisplay = stock.trendSignal.replace("_", " ");
                const tradingSignalLower = stock.tradingSignal.toLowerCase().replace("_", "-");
                const tradingSignalDisplay = stock.tradingSignal.replace("_", " ");
                
                var html = "<td>" + (index + 1) + "</td>" +
                    "<td><strong>" + stock.symbol + "</strong></td>" +
                    "<td>" + stock.companyName + "</td>" +
                    "<td><span class=\\\"" + "market-cap-badge market-cap-" + marketCapLower + "\\\">" + marketCapDisplay + "</span></td>" +
                    "<td>₹" + stock.currentPrice.toLocaleString() + "</td>" +
                    "<td class=\\\"" + change1DClass + "\\\">" + change1DSign + stock.change1D.toFixed(2) + "%</td>" +
                    "<td class=\\\"" + change1WClass + "\\\">" + change1WSign + stock.change1W.toFixed(2) + "%</td>" +
                    "<td class=\\\"" + change1MClass + "\\\">" + change1MSign + stock.change1M.toFixed(2) + "%</td>" +
                    "<td><strong>" + stock.technicalScore.toFixed(1) + "</strong></td>" +
                    "<td>" + stock.rsi.toFixed(1) + "</td>" +
                    "<td class=\\\"" + rsClass + "\\\">" + rsSign + stock.relativeStrength.toFixed(2) + "%</td>" +
                    "<td>" + stock.canSlim + "</td>" +
                    "<td>" + stock.minervini + "</td>" +
                    "<td>" + stock.fundamental.toFixed(1) + "</td>" +
                    "<td><span class=\\\"" + "trend-badge trend-" + trendSignalLower + "\\\">" + trendSignalDisplay + "</span></td>" +
                    "<td><span class=\\\"" + "signal-badge signal-" + tradingSignalLower + "\\\">" + tradingSignalDisplay + "</span></td>";
                row.innerHTML = html;
                
                row.style.cursor = "pointer";
                row.addEventListener("click", function() { showStockDetails(stock); });
                tbody.appendChild(row);
            });
        }

        // Sorting functionality
        function sortTable(column) {
            const tbody = document.getElementById("stocksTableBody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            
            // Remove sort classes from all headers
            document.querySelectorAll(".stocks-table th").forEach(th => {
                th.classList.remove("sort-asc", "sort-desc");
            });
            
            // Determine sort direction
            if (currentSortColumn === column) {
                currentSortDirection = currentSortDirection === "asc" ? "desc" : "asc";
            } else {
                currentSortDirection = "asc";
            }
            currentSortColumn = column;
            
            // Add sort class to current header
            const header = document.querySelector(`th[data-sort="${column}"]`);
            header.classList.add(`sort-${currentSortDirection}`);
            
            // Sort the data
            const sortedData = [...stocksData].sort((a, b) => {
                let aVal, bVal;
                
                switch(column) {
                    case "rank":
                        return currentSortDirection === "asc" ? 0 : 0;
                    case "symbol":
                    case "companyName":
                    case "marketCap":
                    case "trendSignal":
                    case "tradingSignal":
                        aVal = a[column].toString().toLowerCase();
                        bVal = b[column].toString().toLowerCase();
                        break;
                    case "currentPrice":
                    case "change1D":
                    case "change1W":
                    case "change1M":
                    case "technicalScore":
                    case "rsi":
                    case "relativeStrength":
                    case "canSlim":
                    case "minervini":
                    case "fundamental":
                        aVal = parseFloat(a[column]) || 0;
                        bVal = parseFloat(b[column]) || 0;
                        break;
                    default:
                        aVal = a[column];
                        bVal = b[column];
                }
                
                if (aVal < bVal) return currentSortDirection === "asc" ? -1 : 1;
                if (aVal > bVal) return currentSortDirection === "asc" ? 1 : -1;
                return 0;
            });
            
            // Update the table with sorted data
            populateStocksTable(sortedData);
        }

        // Setup table sorting
        function setupTableSorting() {
            document.querySelectorAll(".stocks-table th.sortable").forEach(th => {
                th.addEventListener("click", () => {
                    const column = th.getAttribute("data-sort");
                    sortTable(column);
                });
            });
        }

        // Generate Market Breadth Heat Map
        function generateBreadthHeatmap() {
            const heatmapContainer = document.getElementById("breadthHeatmap");
            heatmapContainer.innerHTML = "";

            // Sort stocks by technical score (highest to lowest)
            const sortedStocks = [...stocksData].sort((a, b) => b.technicalScore - a.technicalScore);

            // Create organized grid with 10 columns and 5 rows
            for (let row = 0; row < 5; row++) {
                // Add row label for top performers
                if (row === 0) {
                    const rowLabel = document.createElement("div");
                    rowLabel.className = "heatmap-row-label";
                    rowLabel.textContent = "🏆 Top 10 Performers (Rank 1-10)";
                    heatmapContainer.appendChild(rowLabel);
                } else if (row === 1) {
                    const rowLabel = document.createElement("div");
                    rowLabel.className = "heatmap-row-label";
                    rowLabel.textContent = "🥈 Strong Performers (Rank 11-20)";
                    heatmapContainer.appendChild(rowLabel);
                } else if (row === 2) {
                    const rowLabel = document.createElement("div");
                    rowLabel.className = "heatmap-row-label";
                    rowLabel.textContent = "🥉 Good Performers (Rank 21-30)";
                    heatmapContainer.appendChild(rowLabel);
                } else if (row === 3) {
                    const rowLabel = document.createElement("div");
                    rowLabel.className = "heatmap-row-label";
                    rowLabel.textContent = "📊 Average Performers (Rank 31-40)";
                    heatmapContainer.appendChild(rowLabel);
                } else if (row === 4) {
                    const rowLabel = document.createElement("div");
                    rowLabel.className = "heatmap-row-label";
                    rowLabel.textContent = "📈 Lower Performers (Rank 41-50)";
                    heatmapContainer.appendChild(rowLabel);
                }

                // Create cells for this row
                for (let col = 0; col < 10; col++) {
                    const index = row * 10 + col;
                    if (index < sortedStocks.length) {
                        const stock = sortedStocks[index];
                        const cell = document.createElement("div");
                        cell.className = `heatmap-cell ${getHeatmapScoreClass(stock.technicalScore)}`;
                        
                        // Use shorter text for mobile or show full symbol on hover
                        const displayText = stock.symbol.length > 4 ? stock.symbol.substring(0, 4) : stock.symbol;
                        cell.textContent = displayText;
                        cell.title = `${stock.companyName} (${stock.symbol})\\nScore: ${stock.technicalScore}\\nSignal: ${stock.tradingSignal}\\nRank: ${index + 1}`;
                        
                        // Add click event to show details
                        cell.addEventListener("click", () => {
                            showStockDetails(stock);
                        });
                        
                        heatmapContainer.appendChild(cell);
                    }
                }
            }
        }

        // Get heat map score class
        function getHeatmapScoreClass(score) {
            if (score >= 80) return "excellent";
            if (score >= 65) return "good";
            if (score >= 50) return "moderate";
            if (score >= 35) return "poor";
            return "very-poor";
        }

        // Show stock details in a beautiful modal
        function showStockDetails(stock) {
            const modal = document.getElementById("stockModal");
            const modalSymbol = document.getElementById("modalStockSymbol");
            const modalDetails = document.getElementById("modalStockDetails");
            
            // Update modal title with company name and symbol
            modalSymbol.textContent = `${stock.companyName} (${stock.symbol})`;
            
            // Create detailed content
            const detailsHTML = `
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Company Name</div>
                        <div class="detail-value">${stock.companyName}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Stock Symbol</div>
                        <div class="detail-value">${stock.symbol}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Technical Score</div>
                        <div class="detail-value">${stock.technicalScore}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Trading Signal</div>
                        <div class="signal-badge-modal signal-${stock.tradingSignal.toLowerCase().replace("_", "-")}-modal">${stock.tradingSignal.replace("_", " ")}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Market Cap</div>
                        <div class="market-cap-badge-modal market-cap-${stock.marketCap.toLowerCase()}-modal">${stock.marketCap.replace("_", " ")}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Current Price</div>
                        <div class="detail-value">₹${stock.currentPrice.toLocaleString()}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">RSI</div>
                        <div class="detail-value">${stock.rsi.toFixed(1)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Relative Strength</div>
                        <div class="detail-value ${stock.relativeStrength >= 0 ? "positive" : "negative"}">${stock.relativeStrength >= 0 ? "+" : ""}${stock.relativeStrength.toFixed(2)}%</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">CAN SLIM Score</div>
                        <div class="detail-value">${stock.canSlim}/25</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Minervini Score</div>
                        <div class="detail-value">${stock.minervini}/20</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Fundamental Score</div>
                        <div class="detail-value">${stock.fundamental.toFixed(1)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Trend Signal</div>
                        <div class="trend-badge-modal trend-${stock.trendSignal.toLowerCase().replace("_", "-")}-modal">${stock.trendSignal.replace("_", " ")}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">1 Day Change</div>
                        <div class="detail-value ${stock.change1D >= 0 ? "positive" : "negative"}">${stock.change1D >= 0 ? "+" : ""}${stock.change1D.toFixed(2)}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">1 Week Change</div>
                        <div class="detail-value ${stock.change1W >= 0 ? "positive" : "negative"}">${stock.change1W >= 0 ? "+" : ""}${stock.change1W.toFixed(2)}%</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">1 Month Change</div>
                        <div class="detail-value ${stock.change1M >= 0 ? "positive" : "negative"}">${stock.change1M >= 0 ? "+" : ""}${stock.change1M.toFixed(2)}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Analysis Date</div>
                        <div class="detail-value">', format(latest_date, "%Y-%m-%d"), '</div>
                    </div>
                </div>
            `;
            
            modalDetails.innerHTML = detailsHTML;
            
            // Show modal with animation
            modal.classList.add("active");
            
            // Load chart data and setup controls
            currentStock = stock;
            loadStockChart(stock.symbol);
            setupChartControls();
            
            // Close modal when clicking outside
            modal.addEventListener("click", function(e) {
                if (e.target === modal) {
                    closeModal();
                }
            });
            
            // Close modal with Escape key
            document.addEventListener("keydown", function(e) {
                if (e.key === "Escape" && modal.classList.contains("active")) {
                    closeModal();
                }
            });
        }
        
        // Close modal function
        function closeModal() {
            const modal = document.getElementById("stockModal");
            modal.classList.remove("active");
            
            // Destroy charts to free memory
            if (stockChart) {
                stockChart.destroy();
                stockChart = null;
            }
            if (volumeChart) {
                volumeChart.destroy();
                volumeChart = null;
            }
        }

        // Filter functionality
        function setupFilters() {
            const filterBtns = document.querySelectorAll(".filter-btn");
            const searchBox = document.getElementById("stockSearch");

            filterBtns.forEach(btn => {
                btn.addEventListener("click", () => {
                    filterBtns.forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    applyFilters();
                });
            });

            searchBox.addEventListener("input", applyFilters);
        }

        function applyFilters() {
            const activeFilter = document.querySelector(".filter-btn.active").dataset.filter;
            const searchTerm = document.getElementById("stockSearch").value.toLowerCase();

            let filteredData = stocksData.filter(stock => {
                const matchesSearch = stock.symbol.toLowerCase().includes(searchTerm) || 
                                    stock.companyName.toLowerCase().includes(searchTerm);
                let matchesFilter = true;

                switch (activeFilter) {
                    case "strong-buy":
                        matchesFilter = stock.tradingSignal === "STRONG_BUY";
                        break;
                    case "buy":
                        matchesFilter = stock.tradingSignal === "BUY";
                        break;
                    case "large-cap":
                        matchesFilter = stock.marketCap === "LARGE_CAP";
                        break;
                    case "mid-cap":
                        matchesFilter = stock.marketCap === "MID_CAP";
                        break;
                    case "small-cap":
                        matchesFilter = stock.marketCap === "SMALL_CAP";
                        break;
                    case "micro-cap":
                        matchesFilter = stock.marketCap === "MICRO_CAP";
                        break;
                }

                return matchesSearch && matchesFilter;
            });

            populateStocksTable(filteredData);
        }

        // Chart variables
        let stockChart = null;
        let volumeChart = null;
        let currentStock = null;
        let fullChartData = null; // Store full chart data
        let currentPeriod = "ALL"; // Current selected period

        // Chart functions
        function loadStockChart(symbol) {
            console.log("Loading chart for symbol:", symbol);
            const chartLoading = document.getElementById("chartLoading");
            const stockChartCanvas = document.getElementById("stockChart");
            const volumeChartCanvas = document.getElementById("volumeChart");
            
            // Show loading
            chartLoading.style.display = "flex";
            stockChartCanvas.style.display = "none";
            volumeChartCanvas.style.display = "none";
            
            // Generate or get chart data
            setTimeout(() => {
                fullChartData = generateSampleChartData(symbol);
                // Filter data based on current period
                const filteredData = filterChartDataByPeriod(fullChartData, currentPeriod);
                createCandlestickChart(filteredData);
                createVolumeChart(filteredData);
                
                // Hide loading, show charts
                chartLoading.style.display = "none";
                stockChartCanvas.style.display = "block";
                volumeChartCanvas.style.display = "block";
            }, 1000);
        }
        
        // Filter chart data by period
        function filterChartDataByPeriod(data, period) {
            if (!data || data.length === 0) return data;
            if (period === "ALL") return data;
            
            const now = new Date();
            const cutoffDate = new Date();
            
            switch(period) {
                case "1M":
                    cutoffDate.setMonth(now.getMonth() - 1);
                    break;
                case "3M":
                    cutoffDate.setMonth(now.getMonth() - 3);
                    break;
                case "6M":
                    cutoffDate.setMonth(now.getMonth() - 6);
                    break;
                case "1Y":
                    cutoffDate.setFullYear(now.getFullYear() - 1);
                    break;
                default:
                    return data;
            }
            
            return data.filter(d => {
                const dataDate = new Date(d.x);
                return dataDate >= cutoffDate;
            });
        }
        
        // Update charts with filtered data
        function updateChartsForPeriod(period) {
            if (!fullChartData || fullChartData.length === 0) {
                console.log("No chart data available to filter");
                return;
            }
            
            currentPeriod = period;
            const filteredData = filterChartDataByPeriod(fullChartData, period);
            
            if (filteredData.length === 0) {
                console.log("No data available for period:", period);
                return;
            }
            
            // Update charts with filtered data
            createCandlestickChart(filteredData);
            createVolumeChart(filteredData);
            
            // Update period info if element exists
            const periodInfo = document.getElementById("chartPeriodInfo");
            if (periodInfo) {
                periodInfo.textContent = "Showing: " + period + " data (" + filteredData.length + " data points)";
            }
        }

        function generateSampleChartData(symbol) {
            // Use real chart data if available
            if (typeof stockChartData !== "undefined" && stockChartData && stockChartData[symbol]) {
                console.log("Using real chart data for", symbol);
                return stockChartData[symbol].map(function(d) {
                    return {
                        x: new Date(d.x),
                        o: d.o,
                        h: d.h,
                        l: d.l,
                        c: d.c,
                        v: d.v,
                        sma20: d.sma20,
                        sma50: d.sma50,
                        sma100: d.sma100,
                        sma200: d.sma200
                    };
                });
            }
            
            // Fallback to sample data
            console.log("Using sample chart data for", symbol);
            const data = [];
            const basePrice = stocksData.find(s => s.symbol === symbol)?.currentPrice || 100;
            let currentPrice = basePrice;
            const startDate = new Date();
            startDate.setDate(startDate.getDate() - 200);
            
            for (let i = 0; i < 200; i++) {
                const date = new Date(startDate);
                date.setDate(date.getDate() + i);
                
                const change = (Math.random() - 0.5) * 0.05;
                const open = currentPrice;
                const close = open * (1 + change);
                const high = Math.max(open, close) * (1 + Math.random() * 0.02);
                const low = Math.min(open, close) * (1 - Math.random() * 0.02);
                const volume = Math.floor(Math.random() * 1000000) + 100000;
                
                data.push({
                    x: date,
                    o: open,
                    h: high,
                    l: low,
                    c: close,
                    v: volume,
                    sma20: null,
                    sma50: null,
                    sma100: null,
                    sma200: null
                });
                
                currentPrice = close;
            }
            
            return data;
        }

        function createCandlestickChart(data) {
            console.log("Creating OHLC chart with data:", data.length, "points");
            const ctx = document.getElementById("stockChart").getContext("2d");
            if (stockChart) { stockChart.destroy(); }
            
            try {
                // Create datasets for OHLC and Moving Averages (using numeric indices)
                const highData = data.map((d, index) => ({ x: index, y: d.h }));
                const lowData = data.map((d, index) => ({ x: index, y: d.l }));
                const openData = data.map((d, index) => ({ x: index, y: d.o }));
                const closeData = data.map((d, index) => ({ x: index, y: d.c }));
                
                // Moving averages data
                const sma20Data = data.map((d, index) => ({ x: index, y: d.sma20 })).filter(d => d.y !== null);
                const sma50Data = data.map((d, index) => ({ x: index, y: d.sma50 })).filter(d => d.y !== null);
                const sma100Data = data.map((d, index) => ({ x: index, y: d.sma100 })).filter(d => d.y !== null);
                const sma200Data = data.map((d, index) => ({ x: index, y: d.sma200 })).filter(d => d.y !== null);

                stockChart = new Chart(ctx, {
                    type: "line",
                    data: {
                        datasets: [
                            { label: "Close", data: closeData, borderColor: "#1976d2", backgroundColor: "rgba(25, 118, 210, 0.1)", borderWidth: 2, pointRadius: 0, fill: true, tension: 0.1 },
                            { label: "SMA 20", data: sma20Data, borderColor: "#ff9800", backgroundColor: "transparent", borderWidth: 1, pointRadius: 0, tension: 0, borderDash: [5, 5] },
                            { label: "SMA 50", data: sma50Data, borderColor: "#9c27b0", backgroundColor: "transparent", borderWidth: 1, pointRadius: 0, tension: 0, borderDash: [5, 5] },
                            { label: "SMA 100", data: sma100Data, borderColor: "#4caf50", backgroundColor: "transparent", borderWidth: 1, pointRadius: 0, tension: 0, borderDash: [5, 5] },
                            { label: "SMA 200", data: sma200Data, borderColor: "#f44336", backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0, borderDash: [5, 5] }
                        ]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: true, position: "top" } },
                        scales: {
                            x: {
                                type: "linear",
                                ticks: {
                                    maxTicksLimit: 10,
                                    callback: function(value, index, values) {
                                        if (data[Math.floor(value)]) {
                                            const date = new Date(data[Math.floor(value)].x);
                                            return date.toLocaleDateString("en-US", { 
                                                month: "short", 
                                                day: "numeric",
                                                year: "numeric"
                                            });
                                        }
                                        return "";
                                    }
                                }
                            },
                            y: { position: "right" }
                        }
                    }
                });
            } catch (error) {
                console.error("Error creating OHLC chart:", error);
            }
        }

        function createVolumeChart(data) {
            const ctx = document.getElementById("volumeChart").getContext("2d");
            if (volumeChart) { volumeChart.destroy(); }
            try {
                const volumeData = data.map((d, index) => ({
                    x: index,
                    y: d.v
                }));
                volumeChart = new Chart(ctx, {
                    type: "bar",
                    data: {
                        datasets: [{ label: "Volume", data: volumeData, backgroundColor: "#1976d2", borderColor: "#1976d2", borderWidth: 1 }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                type: "linear",
                                display: false
                            },
                            y: { position: "right", beginAtZero: true }
                        }
                    }
                });
            } catch (error) { console.error("Error creating volume chart:", error); }
        }

        function setupChartControls() {
            const chartBtns = document.querySelectorAll(".chart-btn");
            chartBtns.forEach(btn => {
                btn.addEventListener("click", () => {
                    chartBtns.forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    const period = btn.dataset.period;
                    console.log(`Filtering chart data for period: ${period}`);
                    updateChartsForPeriod(period);
                });
            });
        }

        // Initialize everything when page loads
        document.addEventListener("DOMContentLoaded", () => {
            console.log("Dashboard initializing...");
            console.log("Stocks data count:", stocksData ? stocksData.length : 0);
            try {
                initializeCharts();
                if (stocksData && stocksData.length > 0) {
                    console.log("Populating table with", stocksData.length, "stocks");
                    populateStocksTable(stocksData);
                } else {
                    console.error("No stocks data available!");
                }
                generateBreadthHeatmap();
                setupFilters();
                setupTableSorting();
                console.log("Dashboard initialized successfully");
            } catch (error) {
                console.error("Error initializing dashboard:", error);
            }
        });
    </script>


</body>
</html>')
  
  # Save HTML file
  html_filename <- paste0(output_dir, "NSE_Interactive_Dashboard_", format(latest_date, "%Y%m%d"), "_", timestamp, ".html")
  writeLines(html_content, html_filename)
  
  cat("HTML dashboard saved to:", html_filename, "\n")
}

# Function for enhanced technical scoring with William O'Neil CAN SLIM and Mark Minervini indicators
calculate_tech_score <- function(stock_data, index_data = NULL, fundamental_data = NULL, symbol = NULL) {
  if(nrow(stock_data) < 50) return(list(score = NA, rsi = NA, trend = NA, relative_strength = NA))
  
  prices <- stock_data$CLOSE
  volumes <- stock_data$TOTTRDQTY
  current_price <- tail(prices, 1)
  
  score <- 0
  
  # RSI Score (10 points) - Reduced weight
  rsi_val <- tryCatch(tail(RSI(prices, n = 14), 1), error = function(e) NA)
  rsi_score <- 0
  if(!is.na(rsi_val)) {
    if(rsi_val > 40 && rsi_val < 70) rsi_score <- 10
    else if(rsi_val > 30 && rsi_val < 80) rsi_score <- 7
    else rsi_score <- 3
  }
  
  # Enhanced Price Trend Score (25 points) - Reduced weight
  trend_score <- 0
  
  # Calculate multiple SMAs
  sma_50 <- tryCatch(tail(SMA(prices, n = 50), 1), error = function(e) NA)
  sma_100 <- tryCatch(tail(SMA(prices, n = 100), 1), error = function(e) NA)
  sma_200 <- tryCatch(tail(SMA(prices, n = 200), 1), error = function(e) NA)
  sma_20 <- tryCatch(tail(SMA(prices, n = 20), 1), error = function(e) NA)
  sma_10 <- tryCatch(tail(SMA(prices, n = 10), 1), error = function(e) NA)
  
  # Price vs SMAs (12 points)
  if(!is.na(sma_200) && current_price > sma_200) trend_score <- trend_score + 3   # Above 200 SMA
  if(!is.na(sma_100) && current_price > sma_100) trend_score <- trend_score + 3   # Above 100 SMA
  if(!is.na(sma_50) && current_price > sma_50) trend_score <- trend_score + 3     # Above 50 SMA
  if(!is.na(sma_20) && current_price > sma_20) trend_score <- trend_score + 2     # Above 20 SMA
  if(!is.na(sma_10) && current_price > sma_10) trend_score <- trend_score + 1     # Above 10 SMA
  
  # SMA Crossovers (13 points)
  if(!is.na(sma_10) && !is.na(sma_20) && sma_10 > sma_20) trend_score <- trend_score + 3    # 10>20 crossover
  if(!is.na(sma_20) && !is.na(sma_50) && sma_20 > sma_50) trend_score <- trend_score + 3    # 20>50 crossover
  if(!is.na(sma_50) && !is.na(sma_100) && sma_50 > sma_100) trend_score <- trend_score + 4  # 50>100 crossover
  if(!is.na(sma_100) && !is.na(sma_200) && sma_100 > sma_200) trend_score <- trend_score + 3 # 100>200 crossover
  
  # Relative Strength Score (25 points) - EQUAL WEIGHT WITH MINERVINI
  relative_strength_score <- 0
  relative_strength <- NA
  
  if(!is.null(index_data) && nrow(index_data) >= 50) {
    # Calculate relative strength (stock performance vs index over last 50 days)
    stock_return <- (current_price / prices[max(1, length(prices)-50)]) - 1
    index_current <- tail(index_data$CLOSE, 1)
    index_50_days_ago <- index_data$CLOSE[max(1, nrow(index_data)-50)]
    index_return <- (index_current / index_50_days_ago) - 1
    
    relative_strength <- stock_return - index_return
    
    if(!is.na(relative_strength)) {
      if(relative_strength > 0.10) relative_strength_score <- 25        # 10%+ outperformance
      else if(relative_strength > 0.07) relative_strength_score <- 22   # 7-10% outperformance
      else if(relative_strength > 0.05) relative_strength_score <- 20   # 5-7% outperformance
      else if(relative_strength > 0.03) relative_strength_score <- 17   # 3-5% outperformance
      else if(relative_strength > 0.01) relative_strength_score <- 15   # 1-3% outperformance
      else if(relative_strength > 0) relative_strength_score <- 12      # 0-1% outperformance
      else if(relative_strength > -0.01) relative_strength_score <- 10  # 0-1% underperformance
      else if(relative_strength > -0.03) relative_strength_score <- 7   # 1-3% underperformance
      else if(relative_strength > -0.05) relative_strength_score <- 5   # 3-5% underperformance
      else if(relative_strength > -0.07) relative_strength_score <- 2   # 5-7% underperformance
      else relative_strength_score <- 0                                # >7% underperformance
    }
  }
  
  # Volume Score (15 points) - Same weight
  volume_score <- 0
  if(length(volumes) >= 10) {
    vol_avg <- mean(tail(volumes, 10), na.rm = TRUE)
    current_vol <- tail(volumes, 1)
    if(!is.na(vol_avg) && !is.na(current_vol)) {
      if(current_vol > vol_avg * 1.5) volume_score <- 15
      else if(current_vol > vol_avg) volume_score <- 10
      else if(current_vol > vol_avg * 0.8) volume_score <- 5
    }
  }
  
  # WILLIAM O'NEIL CAN SLIM INDICATORS (25 points)
  can_slim_score <- 0
  
  # C - Current Quarterly Earnings (5 points)
  # Using price momentum as proxy for earnings growth
  if(length(prices) >= 20) {
    price_20d_ago <- prices[max(1, length(prices)-20)]
    price_momentum_20d <- (current_price / price_20d_ago) - 1
    if(price_momentum_20d > 0.10) can_slim_score <- can_slim_score + 5  # 10%+ growth
    else if(price_momentum_20d > 0.05) can_slim_score <- can_slim_score + 3  # 5-10% growth
    else if(price_momentum_20d > 0) can_slim_score <- can_slim_score + 1  # Positive growth
  }
  
  # A - Annual Earnings Growth (5 points)
  # Using 50-day momentum as proxy for annual growth
  if(length(prices) >= 50) {
    price_50d_ago <- prices[max(1, length(prices)-50)]
    price_momentum_50d <- (current_price / price_50d_ago) - 1
    if(price_momentum_50d > 0.20) can_slim_score <- can_slim_score + 5  # 20%+ growth
    else if(price_momentum_50d > 0.10) can_slim_score <- can_slim_score + 3  # 10-20% growth
    else if(price_momentum_50d > 0.05) can_slim_score <- can_slim_score + 1  # 5-10% growth
  }
  
  # N - New Product/Service/Management (5 points)
  # Using volume surge as proxy for new developments
  if(length(volumes) >= 20) {
    vol_20d_avg <- mean(tail(volumes, 20), na.rm = TRUE)
    current_vol <- tail(volumes, 1)
    if(!is.na(vol_20d_avg) && !is.na(current_vol)) {
      if(current_vol > vol_20d_avg * 2) can_slim_score <- can_slim_score + 5  # 2x volume
      else if(current_vol > vol_20d_avg * 1.5) can_slim_score <- can_slim_score + 3  # 1.5x volume
      else if(current_vol > vol_20d_avg) can_slim_score <- can_slim_score + 1  # Above average
    }
  }
  
  # S - Supply and Demand (5 points)
  # Using price vs moving averages as proxy for supply/demand
  sma_50 <- tryCatch(tail(SMA(prices, n = 50), 1), error = function(e) NA)
  sma_200 <- tryCatch(tail(SMA(prices, n = 200), 1), error = function(e) NA)
  if(!is.na(sma_50) && !is.na(sma_200)) {
    if(current_price > sma_50 && sma_50 > sma_200) can_slim_score <- can_slim_score + 5  # Strong uptrend
    else if(current_price > sma_50) can_slim_score <- can_slim_score + 3  # Above 50 SMA
    else if(current_price > sma_200) can_slim_score <- can_slim_score + 1  # Above 200 SMA
  }
  
  # L - Leader or Laggard (5 points)
  # Using relative strength as proxy for leadership
  if(!is.na(relative_strength)) {
    if(relative_strength > 0.10) can_slim_score <- can_slim_score + 5  # 10%+ outperformance
    else if(relative_strength > 0.05) can_slim_score <- can_slim_score + 3  # 5-10% outperformance
    else if(relative_strength > 0) can_slim_score <- can_slim_score + 1  # Positive outperformance
  }
  
  # MARK MINERVINI TECHNICAL INDICATORS (20 points)
  minervini_score <- 0
  
  # 1. VCP (Volatility Contraction Pattern) - 6 points
  # Calculate recent volatility vs longer-term volatility
  if(length(prices) >= 20) {
    recent_volatility <- sd(tail(prices, 10)) / mean(tail(prices, 10))
    longer_volatility <- sd(tail(prices, 20)) / mean(tail(prices, 20))
    if(!is.na(recent_volatility) && !is.na(longer_volatility) && longer_volatility > 0) {
      volatility_ratio <- recent_volatility / longer_volatility
      if(volatility_ratio < 0.7) minervini_score <- minervini_score + 6  # Strong VCP
      else if(volatility_ratio < 0.9) minervini_score <- minervini_score + 4  # Moderate VCP
      else if(volatility_ratio < 1.1) minervini_score <- minervini_score + 2  # Neutral
    }
  }
  
  # 2. Base Formation - 6 points
  # Check for consolidation pattern (price range over time)
  if(length(prices) >= 30) {
    recent_high <- max(tail(prices, 30))
    recent_low <- min(tail(prices, 30))
    price_range <- (recent_high - recent_low) / recent_low
    if(price_range < 0.15) minervini_score <- minervini_score + 6  # Tight base
    else if(price_range < 0.25) minervini_score <- minervini_score + 4  # Moderate base
    else if(price_range < 0.35) minervini_score <- minervini_score + 2  # Wide base
  }
  
  # 3. Volume Confirmation - 8 points
  # Check for volume increase on price moves
  if(length(volumes) >= 10 && length(prices) >= 10) {
    recent_price_change <- (prices[length(prices)] - prices[length(prices)-1]) / prices[length(prices)-1]
    recent_vol_change <- (volumes[length(volumes)] - volumes[length(volumes)-1]) / volumes[length(volumes)-1]
    
    if(recent_price_change > 0.02 && recent_vol_change > 0.5) minervini_score <- minervini_score + 8  # Strong volume confirmation
    else if(recent_price_change > 0.01 && recent_vol_change > 0.2) minervini_score <- minervini_score + 5  # Moderate volume confirmation
    else if(recent_price_change > 0 && recent_vol_change > 0) minervini_score <- minervini_score + 3  # Weak volume confirmation
  }
  
  # FUNDAMENTAL SCORE INTEGRATION (25 points)
  fundamental_score <- 0
  enhanced_fund_score <- NA
  earnings_quality <- NA
  sales_growth <- NA
  financial_strength <- NA
  institutional_backing <- NA
  
  if(!is.null(fundamental_data) && !is.null(symbol)) {
    # Find fundamental data for this symbol
    fund_row <- fundamental_data[fundamental_data$symbol == symbol, ]
    

    
    if(nrow(fund_row) > 0) {
      enhanced_fund_score <- fund_row$ENHANCED_FUND_SCORE[1]
      earnings_quality <- fund_row$EARNINGS_QUALITY[1]
      sales_growth <- fund_row$SALES_GROWTH[1]
      financial_strength <- fund_row$FINANCIAL_STRENGTH[1]
      institutional_backing <- fund_row$INSTITUTIONAL_BACKING[1]
      
      # Score based on enhanced fundamental score
      if(!is.na(enhanced_fund_score)) {
        if(enhanced_fund_score >= 70) fundamental_score <- 25        # Excellent fundamentals
        else if(enhanced_fund_score >= 60) fundamental_score <- 20   # Good fundamentals
        else if(enhanced_fund_score >= 50) fundamental_score <- 15   # Average fundamentals
        else if(enhanced_fund_score >= 40) fundamental_score <- 10   # Below average
        else if(enhanced_fund_score >= 30) fundamental_score <- 5    # Poor fundamentals
        else fundamental_score <- 0                                  # Very poor fundamentals
      }
    }
  }
  
  # Calculate total score (150 points total with fundamental score)
  total_score <- rsi_score + trend_score + relative_strength_score + volume_score + can_slim_score + minervini_score + fundamental_score
  
  # Normalize score to 0-100 scale (150 points total)
  total_score <- round((total_score / 150) * 100, 1)
  
  # Enhanced trend determination
  trend_signal <- "NEUTRAL"
  bullish_count <- 0
  bearish_count <- 0
  
  # Count bullish/bearish signals
  if(!is.na(sma_10) && !is.na(sma_20) && sma_10 > sma_20) bullish_count <- bullish_count + 1
  if(!is.na(sma_20) && !is.na(sma_50) && sma_20 > sma_50) bullish_count <- bullish_count + 1
  if(!is.na(sma_50) && !is.na(sma_100) && sma_50 > sma_100) bullish_count <- bullish_count + 1
  if(!is.na(sma_100) && !is.na(sma_200) && sma_100 > sma_200) bullish_count <- bullish_count + 1
  
  if(!is.na(sma_10) && !is.na(sma_20) && sma_10 < sma_20) bearish_count <- bearish_count + 1
  if(!is.na(sma_20) && !is.na(sma_50) && sma_20 < sma_50) bearish_count <- bearish_count + 1
  if(!is.na(sma_50) && !is.na(sma_100) && sma_50 < sma_100) bearish_count <- bearish_count + 1
  if(!is.na(sma_100) && !is.na(sma_200) && sma_100 < sma_200) bearish_count <- bearish_count + 1
  
  if(bullish_count >= 3) trend_signal <- "STRONG_BULLISH"
  else if(bullish_count >= 2) trend_signal <- "BULLISH"
  else if(bearish_count >= 3) trend_signal <- "STRONG_BEARISH"
  else if(bearish_count >= 2) trend_signal <- "BEARISH"
  
  return(list(
    score = total_score, 
    rsi = rsi_val, 
    trend = trend_signal, 
    relative_strength = relative_strength,
    can_slim_score = can_slim_score,
    minervini_score = minervini_score,
    fundamental_score = fundamental_score,
    enhanced_fund_score = enhanced_fund_score,
    earnings_quality = earnings_quality,
    sales_growth = sales_growth,
    financial_strength = financial_strength,
    institutional_backing = institutional_backing
  ))
}

# Process all selected stocks with progress tracking
print("Processing selected stocks...")
results <- data.frame()
processed_count <- 0
error_count <- 0

for(i in 1:length(symbols_to_analyze)) {
  symbol <- symbols_to_analyze[i]
  
  if(i %% 100 == 1) {
    print(paste("Processing stock", i, "of", length(symbols_to_analyze), "-", symbol))
  }
  
  tryCatch({
    # Get historical data for this stock (last 200 days)
    stock_data <- dt_stocks %>%
      filter(SYMBOL == symbol & TIMESTAMP >= (latest_date - 200)) %>%
      arrange(TIMESTAMP)
    
    if(nrow(stock_data) >= 50) {
      latest_data <- stock_data %>% filter(TIMESTAMP == latest_date)
      
      if(nrow(latest_data) > 0) {
        # Get corresponding index data for relative strength calculation
        index_data_for_stock <- NULL
        if(!is.null(nifty500_data)) {
          index_data_for_stock <- nifty500_data %>%
            filter(TIMESTAMP >= (latest_date - 200)) %>%
            arrange(TIMESTAMP)
        }
        
        # Calculate enhanced technical score with relative strength and fundamental data
        tech_result <- calculate_tech_score(stock_data, index_data_for_stock, fundamental_data, symbol)
        
        if(!is.na(tech_result$score)) {
          # Determine market cap category based on trading value rank in filtered stocks
          trading_value <- latest_data$TOTTRDVAL[1]
          # Find the rank of this stock in the filtered_stocks dataframe
          stock_rank <- which(filtered_stocks$SYMBOL == symbol)
          market_cap_cat <- case_when(
            stock_rank <= 50 ~ "LARGE_CAP",
            stock_rank <= 150 ~ "MID_CAP", 
            stock_rank <= 300 ~ "SMALL_CAP",
            TRUE ~ "MICRO_CAP"
          )
          
          # Calculate price changes
          current_price <- latest_data$CLOSE[1]
          
          # Convert latest_date to Date object for all calculations
          latest_date_obj <- as.Date(latest_date)
          
          # 1-day change - find closest available date
          day_1_ago <- latest_date_obj - 1
          available_dates_1d <- unique(stock_data$TIMESTAMP)
          available_dates_1d_obj <- as.Date(available_dates_1d)
          date_diffs_1d <- abs(available_dates_1d_obj - day_1_ago)
          closest_date_1d_idx <- which.min(date_diffs_1d)
          closest_date_1d <- available_dates_1d[closest_date_1d_idx]
          
          if(date_diffs_1d[closest_date_1d_idx] <= 2) {  # Within 2 days for 1D
            price_1d_ago <- stock_data %>% 
              filter(TIMESTAMP == closest_date_1d) %>% 
              pull(CLOSE) %>% 
              first()
            change_1d <- ifelse(!is.na(price_1d_ago), 
                               round(((current_price - price_1d_ago) / price_1d_ago) * 100, 2), 
                               NA)
          } else {
            change_1d <- NA
          }
          
          # 1-week change (7 days) - find closest available date
          week_1_ago <- latest_date_obj - 7
          available_dates_1w <- unique(stock_data$TIMESTAMP)
          available_dates_1w_obj <- as.Date(available_dates_1w)
          date_diffs_1w <- abs(available_dates_1w_obj - week_1_ago)
          closest_date_1w_idx <- which.min(date_diffs_1w)
          closest_date_1w <- available_dates_1w[closest_date_1w_idx]
          
          if(date_diffs_1w[closest_date_1w_idx] <= 3) {  # Within 3 days for 1W
            price_1w_ago <- stock_data %>% 
              filter(TIMESTAMP == closest_date_1w) %>% 
              pull(CLOSE) %>% 
              first()
            change_1w <- ifelse(!is.na(price_1w_ago), 
                               round(((current_price - price_1w_ago) / price_1w_ago) * 100, 2), 
                               NA)
          } else {
            change_1w <- NA
          }
          
          # 1-month change (30 days) - properly fixed date calculation
          month_1_ago <- latest_date_obj - 30
          
          # Find the closest available date within ±5 days of 30 days ago
          available_dates <- unique(stock_data$TIMESTAMP)
          available_dates_obj <- as.Date(available_dates)
          
          # Find the closest date within ±5 days
          date_diffs <- abs(available_dates_obj - month_1_ago)
          closest_date_idx <- which.min(date_diffs)
          closest_date <- available_dates[closest_date_idx]
          
          # Only use if the closest date is within 5 days of target
          if(date_diffs[closest_date_idx] <= 5) {
            price_1m_ago <- stock_data %>%
              filter(TIMESTAMP == closest_date) %>%
              pull(CLOSE) %>%
              first()
            change_1m <- ifelse(!is.na(price_1m_ago),
                               round(((current_price - price_1m_ago) / price_1m_ago) * 100, 2),
                               NA)
          } else {
            change_1m <- NA
          }
          
          # Get company name from mapping
          company_name <- symbol  # Default to symbol if no mapping found
          if(!is.null(company_names_data)) {
            company_row <- company_names_data[company_names_data$SYMBOL == symbol, ]
            if(nrow(company_row) > 0) {
              company_name <- company_row$COMPANY_NAME[1]
            }
          }
          
          # Create result record with price changes and new indicators
          result <- data.frame(
            RANK = i,
            SYMBOL = symbol,
            COMPANY_NAME = company_name,
            MARKET_CAP_CATEGORY = market_cap_cat,
            CURRENT_PRICE = round(current_price, 2),
            CHANGE_1D = change_1d,
            CHANGE_1W = change_1w,
            CHANGE_1M = change_1m,
            TECHNICAL_SCORE = tech_result$score,
            RSI = round(ifelse(is.na(tech_result$rsi), 0, tech_result$rsi), 1),
            TREND_SIGNAL = tech_result$trend,
            RELATIVE_STRENGTH = round(ifelse(is.na(tech_result$relative_strength), 0, tech_result$relative_strength * 100), 2),
            CAN_SLIM_SCORE = tech_result$can_slim_score,
            MINERVINI_SCORE = tech_result$minervini_score,
            FUNDAMENTAL_SCORE = tech_result$fundamental_score,
            ENHANCED_FUND_SCORE = tech_result$enhanced_fund_score,
            EARNINGS_QUALITY = tech_result$earnings_quality,
            SALES_GROWTH = tech_result$sales_growth,
            FINANCIAL_STRENGTH = tech_result$financial_strength,
            INSTITUTIONAL_BACKING = tech_result$institutional_backing,
            TRADING_VALUE = trading_value,
            TRADING_SIGNAL = case_when(
              tech_result$score >= 80 ~ "STRONG_BUY",
              tech_result$score >= 65 ~ "BUY",
              tech_result$score >= 50 ~ "HOLD", 
              tech_result$score >= 35 ~ "WEAK_HOLD",
              TRUE ~ "SELL"
            ),
            ANALYSIS_DATE = latest_date,
            stringsAsFactors = FALSE
          )
          
          results <- rbind(results, result)
          processed_count <- processed_count + 1
        }
      }
    }
  }, error = function(e) {
    error_count <- error_count + 1
    # Skip problematic stocks silently
  })
}

print(paste("Processing completed. Successfully processed:", processed_count, "stocks. Errors:", error_count))

# Analyze NSE indices
cat("\nAnalyzing NSE indices...\n")
index_results <- analyze_nse_indices(index_data, latest_date)
cat("Index analysis completed. Analyzed", nrow(index_results), "indices.\n")

# Sort by technical score
results <- results %>% arrange(desc(TECHNICAL_SCORE))

# Generate comprehensive summary
if(nrow(results) > 0) {
  cat("\n===============================================================================\n")
  cat("COMPREHENSIVE NSE STOCK UNIVERSE ANALYSIS\n")
  cat("Analysis Date:", as.character(latest_date), "\n")
  cat("===============================================================================\n\n")
  
  # Overall summary
  total_analyzed <- nrow(results)
  
  signal_dist <- results %>%
    group_by(TRADING_SIGNAL) %>%
    summarise(COUNT = n(), .groups = 'drop') %>%
    mutate(PERCENTAGE = round(COUNT/total_analyzed*100, 1))
  
  cap_dist <- results %>%
    group_by(MARKET_CAP_CATEGORY) %>%
    summarise(COUNT = n(), AVG_SCORE = round(mean(TECHNICAL_SCORE), 1), .groups = 'drop')
  
  cat("ANALYSIS SUMMARY:\n")
  cat("Total Stocks Analyzed:", total_analyzed, "\n")
  cat("Filtering Criteria: Price > ₹100 & Volume > 100,000\n")
  cat("Analysis Coverage: Filtered universe analysis\n\n")
  
  cat("TRADING SIGNALS DISTRIBUTION:\n")
  print(signal_dist)
  cat("\n")
  
  cat("MARKET CAP CATEGORY PERFORMANCE:\n")
  print(cap_dist)
  cat("\n")
  
  # Top performers
  cat("TOP 15 STOCKS BY TECHNICAL SCORE:\n")
  top_15 <- head(results, 15)
  print(top_15[, c("SYMBOL", "MARKET_CAP_CATEGORY", "CURRENT_PRICE", "CHANGE_1D", "CHANGE_1W", "CHANGE_1M", "TECHNICAL_SCORE", "RSI", "RELATIVE_STRENGTH", "CAN_SLIM_SCORE", "MINERVINI_SCORE", "TREND_SIGNAL", "TRADING_SIGNAL")])
  
  cat("\nTOP PERFORMERS BY CATEGORY:\n")
  for(category in unique(results$MARKET_CAP_CATEGORY)) {
    cat("\n", category, " TOP 5:\n")
    category_top <- results %>%
      filter(MARKET_CAP_CATEGORY == category) %>%
      head(5)
    print(category_top[, c("SYMBOL", "CURRENT_PRICE", "CHANGE_1D", "CHANGE_1W", "CHANGE_1M", "TECHNICAL_SCORE", "RELATIVE_STRENGTH", "CAN_SLIM_SCORE", "MINERVINI_SCORE", "TREND_SIGNAL", "TRADING_SIGNAL")])
  }
  
  # Strong buy recommendations
  strong_buys <- results %>% filter(TRADING_SIGNAL == "STRONG_BUY")
  cat("\nSTRONG BUY RECOMMENDATIONS (Score >= 80):\n")
  cat("Total Strong Buys:", nrow(strong_buys), "\n")
  if(nrow(strong_buys) > 0) {
    print(strong_buys[, c("SYMBOL", "MARKET_CAP_CATEGORY", "CURRENT_PRICE", "CHANGE_1D", "CHANGE_1W", "CHANGE_1M", "TECHNICAL_SCORE", "RSI", "RELATIVE_STRENGTH", "CAN_SLIM_SCORE", "MINERVINI_SCORE", "TREND_SIGNAL")])
  }
  
  # TOP 5 INDICES STOCKS ANALYSIS
  cat("\n===============================================================================\n")
  cat("TOP 5 INDICES - TOP 5 STOCKS ANALYSIS\n")
  cat("===============================================================================\n\n")
  
  # Define the top 5 indices based on our index analysis
  top_5_indices <- c("Nifty Auto", "Nifty FMCG", "Nifty Pharma", "Nifty Metal", "Nifty 50")
  
  # Define index constituents (major stocks in each index)
  index_constituents <- list(
    "Nifty Auto" = c("MARUTI", "TATAMOTORS", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "ASHOKLEY", "M&M", "TVSMOTOR", "MRF", "APOLLOTYRE"),
    "Nifty FMCG" = c("HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO", "COLPAL", "GODREJCP", "UBL", "VBL"),
    "Nifty Pharma" = c("SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "BIOCON", "TORNTPHARM", "ALKEM", "LUPIN", "AUROPHARMA"),
    "Nifty Metal" = c("TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "HINDCOPPER", "NATIONALUM", "SAIL", "WELCORP", "JINDALSTEL"),
    "Nifty 50" = c("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", 
                   "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA", "TATAMOTORS", "WIPRO", "ULTRACEMCO", "TITAN", "BAJFINANCE", "NESTLEIND")
  )
  
  # Analyze top 5 stocks from each index
  for(index_name in top_5_indices) {
    cat("\n", toupper(index_name), " - TOP 5 STOCKS BY TECHNICAL SCORE:\n")
    cat("=", paste(rep("=", nchar(index_name) + 30)), "\n")
    
    # Get constituents for this index
    constituents <- index_constituents[[index_name]]
    
    if(!is.null(constituents)) {
      # Filter results for this index's constituents
      index_stocks <- results %>%
        filter(SYMBOL %in% constituents) %>%
        arrange(desc(TECHNICAL_SCORE)) %>%
        head(5)
      
              if(nrow(index_stocks) > 0) {
          print(index_stocks[, c("SYMBOL", "MARKET_CAP_CATEGORY", "CURRENT_PRICE", "CHANGE_1D", "CHANGE_1W", "CHANGE_1M", "TECHNICAL_SCORE", "RSI", "RELATIVE_STRENGTH", "CAN_SLIM_SCORE", "MINERVINI_SCORE", "TREND_SIGNAL", "TRADING_SIGNAL")])
        
        # Summary for this index
        avg_score <- round(mean(index_stocks$TECHNICAL_SCORE), 1)
        strong_buy_count <- sum(index_stocks$TRADING_SIGNAL == "STRONG_BUY")
        buy_count <- sum(index_stocks$TRADING_SIGNAL == "BUY")
        
        cat("\nIndex Summary:\n")
        cat("• Average Technical Score:", avg_score, "\n")
        cat("• Strong Buy Signals:", strong_buy_count, "\n")
        cat("• Buy Signals:", buy_count, "\n")
        cat("• Top Performer:", index_stocks$SYMBOL[1], " (Score:", index_stocks$TECHNICAL_SCORE[1], ")\n")
        
      } else {
        cat("No constituent stocks found in analysis results.\n")
      }
    } else {
      cat("Index constituents not defined.\n")
    }
  }
  
  # Overall top indices summary
  cat("\n===============================================================================\n")
  cat("TOP INDICES OVERALL SUMMARY:\n")
  cat("===============================================================================\n")
  
  index_summary <- data.frame()
  for(index_name in top_5_indices) {
    constituents <- index_constituents[[index_name]]
    if(!is.null(constituents)) {
      index_stocks <- results %>%
        filter(SYMBOL %in% constituents) %>%
        arrange(desc(TECHNICAL_SCORE)) %>%
        head(5)
      
      if(nrow(index_stocks) > 0) {
        summary_row <- data.frame(
          INDEX = index_name,
          AVG_SCORE = round(mean(index_stocks$TECHNICAL_SCORE), 1),
          TOP_STOCK = index_stocks$SYMBOL[1],
          TOP_SCORE = index_stocks$TECHNICAL_SCORE[1],
          STRONG_BUY_COUNT = sum(index_stocks$TRADING_SIGNAL == "STRONG_BUY"),
          BUY_COUNT = sum(index_stocks$TRADING_SIGNAL == "BUY"),
          stringsAsFactors = FALSE
        )
        index_summary <- rbind(index_summary, summary_row)
      }
    }
  }
  
  if(nrow(index_summary) > 0) {
    print(index_summary)
  }
  
  # Save results with timestamp in Unified-NSE-Analysis directory
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  filename <- paste0(output_dir, "comprehensive_nse_enhanced_", format(latest_date, "%d%m%Y"), "_", timestamp, ".csv")
  write.csv(results, filename, row.names = FALSE)
  
  # Create database tables first
  cat("\nCreating database tables...\n")
  create_database_tables(db_path)
  
  # Save results to database
  cat("\nSaving results to database...\n")
  save_stocks_to_database(results, latest_date, db_path)
  save_indices_to_database(index_results, latest_date, db_path)
  save_market_breadth_to_database(results, latest_date, db_path)
  
  # Generate comprehensive markdown report
cat("\nGenerating comprehensive markdown report...\n")
generate_markdown_report(results, index_results, latest_date, timestamp, output_dir)
  
  # HTML dashboard will be generated after long-term screeners
  
  # Display enhanced scoring formula explanation
  cat("\nENHANCED TECHNICAL SCORING FORMULA (0-100 scale) - WITH FUNDAMENTAL INTEGRATION:\n")
  cat("• RSI Score (8 points): Optimal range 40-70\n")
  cat("• Price vs SMAs (10 points): Above 10,20,50,100,200 SMAs\n")
  cat("• SMA Crossovers (10 points): 10>20, 20>50, 50>100, 100>200\n")
  cat("• Relative Strength (20 points): vs NIFTY500 over 50 days\n")
  cat("• Volume Score (12 points): vs 10-day average\n")
  cat("• CAN SLIM Score (20 points): William O'Neil methodology\n")
  cat("  - C (Current Earnings): 20-day momentum (4 points)\n")
  cat("  - A (Annual Growth): 50-day momentum (4 points)\n")
  cat("  - N (New Developments): Volume surge (4 points)\n")
  cat("  - S (Supply/Demand): Price vs SMAs (4 points)\n")
  cat("  - L (Leadership): Relative strength (4 points)\n")
  cat("• Minervini Score (20 points): Mark Minervini methodology\n")
  cat("  - VCP (Volatility Contraction): 6 points\n")
  cat("  - Base Formation: 6 points\n")
  cat("  - Volume Confirmation: 8 points\n")
  cat("• Fundamental Score (25 points): Enhanced fundamental analysis\n")
  cat("  - Enhanced Fund Score: 25 points (≥70: 25, ≥60: 20, ≥50: 15, ≥40: 10, ≥30: 5, <30: 0)\n")
  cat("• Total Raw Score: 150 points, normalized to 0-100 scale\n")
  cat("• Trading Signals: STRONG_BUY (≥80), BUY (≥65), HOLD (≥50), WEAK_HOLD (≥35), SELL (<35)\n")
  cat("• Trend Signals: STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, STRONG_BEARISH\n\n")
  
  cat("\nINDEX SCORING FORMULA (100 points total):\n")
  cat("• RSI Score (10 points): Optimal range 40-70\n")
  cat("• Price Trend Score (25 points): Price vs SMAs + SMA crossovers\n")
  cat("• Relative Strength (20 points): vs NIFTY500 over 50 days\n")
  cat("• Momentum Score (30 points): 50-day momentum performance\n")
  cat("• Volume Score (15 points): Current volume vs 10-day average\n")
  cat("• Trading Signals: STRONG_BUY (≥80), BUY (≥65), HOLD (≥50), WEAK_HOLD (≥35), SELL (<35)\n\n")
  
  # =============================================================================
  # LONG-TERM PERSPECTIVE SCREENERS
  # =============================================================================
  
  cat("\n===============================================================================\n")
  cat("LONG-TERM PERSPECTIVE SCREENERS\n")
  cat("===============================================================================\n")
  
  # Function to calculate monthly relative strength
  calculate_monthly_rs <- function(stock_data, index_data, months = 3) {
    if(nrow(stock_data) < 60) return(NA) # Need at least 3 months of data
    
    # Get last 3 months of data
    recent_stock <- tail(stock_data, 60)
    recent_index <- tail(index_data, 60)
    
    if(nrow(recent_stock) < 60 || nrow(recent_index) < 60) return(NA)
    
    # Calculate returns
    stock_return <- (tail(recent_stock$CLOSE, 1) - head(recent_stock$CLOSE, 1)) / head(recent_stock$CLOSE, 1) * 100
    index_return <- (tail(recent_index$CLOSE, 1) - head(recent_index$CLOSE, 1)) / head(recent_index$CLOSE, 1) * 100
    
    # Calculate relative strength
    if(index_return != 0) {
      rs <- stock_return / index_return
    } else {
      rs <- NA
    }
    
    return(rs)
  }
  
  # Function to detect consolidation breakout
  detect_consolidation_breakout <- function(stock_data, months = 3) {
    if(nrow(stock_data) < 60) return(FALSE)
    
    # Get last 3 months of data
    recent_data <- tail(stock_data, 60)
    
    # Calculate price range
    high_price <- max(recent_data$HIGH)
    low_price <- min(recent_data$LOW)
    current_price <- tail(recent_data$CLOSE, 1)
    
    # Check if price is breaking out of consolidation
    consolidation_range <- (high_price - low_price) / low_price * 100
    breakout_threshold <- 2.0 # 2% above recent high
    
    # Consolidation criteria: range < 15% and current price > recent high
    is_consolidation <- consolidation_range < 15
    is_breakout <- current_price > (high_price * (1 + breakout_threshold/100))
    
    return(is_consolidation && is_breakout)
  }
  
  # Function to detect cup and handle pattern
  detect_cup_handle <- function(stock_data) {
    if(nrow(stock_data) < 100) return(FALSE)
    
    # Get last 6 months of data
    recent_data <- tail(stock_data, 120)
    
    # Find the highest point (cup rim)
    max_idx <- which.max(recent_data$HIGH)
    cup_high <- recent_data$HIGH[max_idx]
    
    # Check if we have enough data after the cup
    if(max_idx < 20 || (nrow(recent_data) - max_idx) < 20) return(FALSE)
    
    # Cup formation (decline and recovery)
    cup_data <- recent_data[1:max_idx, ]
    handle_data <- recent_data[(max_idx+1):nrow(recent_data), ]
    
    # Cup criteria: decline of at least 20% and recovery to at least 80% of high
    cup_low <- min(cup_data$LOW)
    cup_decline <- (cup_high - cup_low) / cup_high * 100
    cup_recovery <- tail(cup_data$CLOSE, 1) / cup_high
    
    # Handle criteria: small decline (5-15%) and current price near cup high
    handle_low <- min(handle_data$LOW)
    handle_decline <- (cup_high - handle_low) / cup_high * 100
    current_price <- tail(recent_data$CLOSE, 1)
    near_high <- current_price > (cup_high * 0.95)
    
    # Pattern criteria
    valid_cup <- cup_decline >= 20 && cup_recovery >= 0.8
    valid_handle <- handle_decline >= 5 && handle_decline <= 15 && near_high
    
    return(valid_cup && valid_handle)
  }
  
  # Function to detect long-term uptrend
  detect_long_term_uptrend <- function(stock_data, months = 6) {
    if(nrow(stock_data) < 120) return(FALSE)
    
    # Get last 6 months of data
    recent_data <- tail(stock_data, 120)
    
    # Calculate moving averages
    sma_20 <- mean(tail(recent_data$CLOSE, 20))
    sma_50 <- mean(tail(recent_data$CLOSE, 50))
    sma_100 <- mean(recent_data$CLOSE)
    
    # Check if all SMAs are in ascending order (uptrend)
    sma_uptrend <- sma_20 > sma_50 && sma_50 > sma_100
    
    # Check if price is above all SMAs
    current_price <- tail(recent_data$CLOSE, 1)
    above_smas <- current_price > sma_20 && current_price > sma_50 && current_price > sma_100
    
    # Check for consistent higher highs and higher lows
    highs <- recent_data$HIGH
    lows <- recent_data$LOW
    
    # Simple trend check: recent highs > earlier highs, recent lows > earlier lows
    recent_highs <- tail(highs, 30)
    earlier_highs <- head(highs, 30)
    recent_lows <- tail(lows, 30)
    earlier_lows <- head(lows, 30)
    
    higher_highs <- mean(recent_highs) > mean(earlier_highs)
    higher_lows <- mean(recent_lows) > mean(earlier_lows)
    
    return(sma_uptrend && above_smas && higher_highs && higher_lows)
  }
  
  # Function to detect momentum breakout
  detect_momentum_breakout <- function(stock_data) {
    if(nrow(stock_data) < 50) return(FALSE)
    
    recent_data <- tail(stock_data, 50)
    
    # Calculate momentum indicators
    current_price <- tail(recent_data$CLOSE, 1)
    price_20d_ago <- head(recent_data$CLOSE, 1)
    price_10d_ago <- tail(recent_data$CLOSE, 10)[1]
    
    # 20-day momentum
    momentum_20d <- (current_price - price_20d_ago) / price_20d_ago * 100
    
    # 10-day momentum
    momentum_10d <- (current_price - price_10d_ago) / price_10d_ago * 100
    
    # Volume surge (current volume vs 20-day average)
    current_volume <- tail(recent_data$TOTTRDQTY, 1)
    avg_volume <- mean(recent_data$TOTTRDQTY)
    volume_surge <- current_volume / avg_volume
    
    # Breakout criteria: strong momentum + volume surge
    strong_momentum <- momentum_20d > 15 && momentum_10d > 5
    volume_confirmation <- volume_surge > 1.5
    
    return(strong_momentum && volume_confirmation)
  }
  
  # Function to detect support bounce
  detect_support_bounce <- function(stock_data) {
    if(nrow(stock_data) < 100) return(FALSE)
    
    recent_data <- tail(stock_data, 100)
    
    # Find recent low (support level)
    recent_low <- min(recent_data$LOW)
    low_date <- recent_data$TIMESTAMP[which.min(recent_data$LOW)]
    
    # Check if current price is above support and bouncing
    current_price <- tail(recent_data$CLOSE, 1)
    bounce_threshold <- recent_low * 1.05  # 5% above support
    
    # Check if price bounced from support in last 20 days
    recent_20d <- tail(recent_data, 20)
    touched_support <- any(recent_20d$LOW <= recent_low * 1.02)
    current_above_support <- current_price > bounce_threshold
    
    return(touched_support && current_above_support)
  }
  
  # Function to detect volume accumulation
  detect_volume_accumulation <- function(stock_data) {
    if(nrow(stock_data) < 50) return(FALSE)
    
    recent_data <- tail(stock_data, 50)
    
    # Calculate volume trend
    recent_volume <- tail(recent_data$TOTTRDQTY, 20)
    earlier_volume <- head(recent_data$TOTTRDQTY, 20)
    
    avg_recent_volume <- mean(recent_volume)
    avg_earlier_volume <- mean(earlier_volume)
    
    # Volume increase
    volume_increase <- avg_recent_volume / avg_earlier_volume
    
    # Price stability during volume increase
    recent_prices <- tail(recent_data$CLOSE, 20)
    price_volatility <- sd(recent_prices) / mean(recent_prices) * 100
    
    # Accumulation criteria: volume increase with low price volatility
    volume_surge <- volume_increase > 1.3
    price_stable <- price_volatility < 5
    
    return(volume_surge && price_stable)
  }
  
  # Function to detect earnings momentum
  detect_earnings_momentum <- function(stock_data) {
    if(nrow(stock_data) < 60) return(FALSE)
    
    recent_data <- tail(stock_data, 60)
    
    # Calculate price momentum over different periods
    current_price <- tail(recent_data$CLOSE, 1)
    price_1m <- tail(recent_data$CLOSE, 20)[1]
    price_2m <- tail(recent_data$CLOSE, 40)[1]
    price_3m <- head(recent_data$CLOSE, 1)
    
    # Calculate returns
    ret_1m <- (current_price - price_1m) / price_1m * 100
    ret_2m <- (current_price - price_2m) / price_2m * 100
    ret_3m <- (current_price - price_3m) / price_3m * 100
    
    # Earnings momentum: accelerating returns
    momentum_acceleration <- ret_1m > ret_2m && ret_2m > ret_3m
    positive_momentum <- ret_1m > 5 && ret_2m > 10 && ret_3m > 15
    
    return(momentum_acceleration && positive_momentum)
  }
  
  # Function to detect 52-week high breakouts
  detect_52week_high_breakout <- function(stock_data) {
    if(nrow(stock_data) < 252) return(FALSE)  # Need at least 1 year of data
    
    recent_data <- tail(stock_data, 252)  # Last 1 year
    
    # Get current price and 52-week high
    current_price <- tail(recent_data$CLOSE, 1)
    high_52w <- max(recent_data$HIGH)
    
    # Check if current price is within 2% of 52-week high (breakout zone)
    breakout_threshold <- high_52w * 0.98  # Within 2% of 52-week high
    is_near_high <- current_price >= breakout_threshold
    
    # Additional criteria: volume confirmation
    current_volume <- tail(recent_data$TOTTRDQTY, 1)
    avg_volume_20d <- mean(tail(recent_data$TOTTRDQTY, 20))
    volume_surge <- current_volume / avg_volume_20d > 1.2  # 20% above average
    
    # Price momentum: should be in uptrend
    sma_20 <- mean(tail(recent_data$CLOSE, 20))
    sma_50 <- mean(tail(recent_data$CLOSE, 50))
    uptrend <- sma_20 > sma_50 && current_price > sma_20
    
    return(is_near_high && volume_surge && uptrend)
  }
  
  # Apply long-term screeners to analyzed stocks
  cat("Applying long-term perspective screeners...\n")
  
  long_term_results <- data.frame()
  
  for(i in 1:nrow(results)) {
    symbol <- results$SYMBOL[i]
    
    # Get stock data
    stock_data <- dt_stocks[dt_stocks$SYMBOL == symbol, ]
    stock_data <- stock_data[order(stock_data$TIMESTAMP), ]
    
    if(nrow(stock_data) < 120) next # Need at least 6 months of data
    
    # Get NIFTY500 data for relative strength calculation
    nifty500_data <- dt_index[dt_index$SYMBOL == "Nifty 500", ]
    nifty500_data <- nifty500_data[order(nifty500_data$TIMESTAMP), ]
    
    # Apply screeners
    monthly_rs <- calculate_monthly_rs(stock_data, nifty500_data, 3)
    consolidation_breakout <- detect_consolidation_breakout(stock_data, 3)
    cup_handle <- detect_cup_handle(stock_data)
    long_term_uptrend <- detect_long_term_uptrend(stock_data, 6)
    momentum_breakout <- detect_momentum_breakout(stock_data)
    support_bounce <- detect_support_bounce(stock_data)
    volume_accumulation <- detect_volume_accumulation(stock_data)
    earnings_momentum <- detect_earnings_momentum(stock_data)
    week52_high_breakout <- detect_52week_high_breakout(stock_data)
    
    # Create result row
    result_row <- data.frame(
      SYMBOL = symbol,
      CURRENT_PRICE = tail(stock_data$CLOSE, 1),
      MONTHLY_RS = round(monthly_rs, 2),
      CONSOLIDATION_BREAKOUT = consolidation_breakout,
      CUP_HANDLE = cup_handle,
      LONG_TERM_UPTREND = long_term_uptrend,
      MOMENTUM_BREAKOUT = momentum_breakout,
      SUPPORT_BOUNCE = support_bounce,
      VOLUME_ACCUMULATION = volume_accumulation,
      EARNINGS_MOMENTUM = earnings_momentum,
      WEEK52_HIGH_BREAKOUT = week52_high_breakout,
      TECHNICAL_SCORE = results$TECHNICAL_SCORE[i],
      MARKET_CAP_CATEGORY = results$MARKET_CAP_CATEGORY[i],
      stringsAsFactors = FALSE
    )
    
    long_term_results <- rbind(long_term_results, result_row)
  }
  
  # 1. Strong Monthly Relative Strength
  cat("\n1. STOCKS WITH STRONG MONTHLY RELATIVE STRENGTH (RS > 1.5):\n")
  strong_rs_stocks <- long_term_results[!is.na(long_term_results$MONTHLY_RS) & 
                                       long_term_results$MONTHLY_RS > 1.5, ]
  strong_rs_stocks <- strong_rs_stocks[order(-strong_rs_stocks$MONTHLY_RS), ]
  
  if(nrow(strong_rs_stocks) > 0) {
    print(head(strong_rs_stocks, 10))
    cat("Total stocks with strong monthly RS:", nrow(strong_rs_stocks), "\n")
  } else {
    cat("No stocks found with strong monthly relative strength.\n")
  }
  
  # 2. Consolidation Breakouts
  cat("\n2. STOCKS BREAKING OUT OF 3-4 MONTH CONSOLIDATION:\n")
  breakout_stocks <- long_term_results[long_term_results$CONSOLIDATION_BREAKOUT == TRUE, ]
  breakout_stocks <- breakout_stocks[order(-breakout_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(breakout_stocks) > 0) {
    print(head(breakout_stocks, 10))
    cat("Total consolidation breakouts:", nrow(breakout_stocks), "\n")
  } else {
    cat("No stocks found breaking out of consolidation.\n")
  }
  
  # 3. Cup and Handle Patterns
  cat("\n3. STOCKS WITH CUP AND HANDLE PATTERNS:\n")
  cup_handle_stocks <- long_term_results[long_term_results$CUP_HANDLE == TRUE, ]
  cup_handle_stocks <- cup_handle_stocks[order(-cup_handle_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(cup_handle_stocks) > 0) {
    print(head(cup_handle_stocks, 10))
    cat("Total cup and handle patterns:", nrow(cup_handle_stocks), "\n")
  } else {
    cat("No stocks found with cup and handle patterns.\n")
  }
  
  # 4. Long-term Uptrend
  cat("\n4. STOCKS IN CONSISTENT LONG-TERM UPTREND:\n")
  uptrend_stocks <- long_term_results[long_term_results$LONG_TERM_UPTREND == TRUE, ]
  uptrend_stocks <- uptrend_stocks[order(-uptrend_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(uptrend_stocks) > 0) {
    print(head(uptrend_stocks, 10))
    cat("Total stocks in long-term uptrend:", nrow(uptrend_stocks), "\n")
  } else {
    cat("No stocks found in consistent long-term uptrend.\n")
  }
  
  # 5. Additional Screeners
  cat("\n5. MOMENTUM BREAKOUTS:\n")
  momentum_stocks <- long_term_results[long_term_results$MOMENTUM_BREAKOUT == TRUE, ]
  momentum_stocks <- momentum_stocks[order(-momentum_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(momentum_stocks) > 0) {
    print(head(momentum_stocks, 10))
    cat("Total momentum breakouts:", nrow(momentum_stocks), "\n")
  } else {
    cat("No stocks found with momentum breakouts.\n")
  }
  
  # 6. Support Bounce
  cat("\n6. SUPPORT BOUNCE PATTERNS:\n")
  support_stocks <- long_term_results[long_term_results$SUPPORT_BOUNCE == TRUE, ]
  support_stocks <- support_stocks[order(-support_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(support_stocks) > 0) {
    print(head(support_stocks, 10))
    cat("Total support bounces:", nrow(support_stocks), "\n")
  } else {
    cat("No stocks found with support bounce patterns.\n")
  }
  
  # 7. Volume Accumulation
  cat("\n7. VOLUME ACCUMULATION PATTERNS:\n")
  volume_stocks <- long_term_results[long_term_results$VOLUME_ACCUMULATION == TRUE, ]
  volume_stocks <- volume_stocks[order(-volume_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(volume_stocks) > 0) {
    print(head(volume_stocks, 10))
    cat("Total volume accumulation patterns:", nrow(volume_stocks), "\n")
  } else {
    cat("No stocks found with volume accumulation patterns.\n")
  }
  
  # 8. Earnings Momentum
  cat("\n8. EARNINGS MOMENTUM PATTERNS:\n")
  earnings_stocks <- long_term_results[long_term_results$EARNINGS_MOMENTUM == TRUE, ]
  earnings_stocks <- earnings_stocks[order(-earnings_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(earnings_stocks) > 0) {
    print(head(earnings_stocks, 10))
    cat("Total earnings momentum patterns:", nrow(earnings_stocks), "\n")
  } else {
    cat("No stocks found with earnings momentum patterns.\n")
  }
  
  # 9. 52-Week High Breakouts
  cat("\n9. 52-WEEK HIGH BREAKOUTS:\n")
  week52_stocks <- long_term_results[long_term_results$WEEK52_HIGH_BREAKOUT == TRUE, ]
  week52_stocks <- week52_stocks[order(-week52_stocks$TECHNICAL_SCORE), ]
  
  if(nrow(week52_stocks) > 0) {
    print(head(week52_stocks, 10))
    cat("Total 52-week high breakouts:", nrow(week52_stocks), "\n")
  } else {
    cat("No stocks found breaking 52-week highs.\n")
  }
  
  # 10. Index Rotation Analysis
  cat("\n10. INDEX ROTATION ANALYSIS:\n")
  
  # Calculate index performance
  index_performance <- data.frame()
  
  # Define major indices for rotation analysis
  major_indices <- c("Nifty 50", "Nifty Next 50", "Nifty 100", "Nifty 200", "Nifty 500",
                     "Nifty Midcap 50", "Nifty Midcap 100", "Nifty Midcap 150",
                     "NIFTY SMLCAP 50", "NIFTY SMLCAP 100", "NIFTY SMLCAP 250",
                     "Nifty Auto", "Nifty Bank", "Nifty IT", "Nifty Pharma", "Nifty FMCG",
                     "Nifty Metal", "Nifty Energy", "Nifty Realty", "Nifty Media")
  
  for(index in major_indices) {
    index_data <- dt_index[dt_index$SYMBOL == index, ]
    if(nrow(index_data) < 60) next
    
    index_data <- index_data[order(index_data$TIMESTAMP), ]
    
    # Calculate 1M, 3M, 6M performance
    current_price <- tail(index_data$CLOSE, 1)
    price_1m <- tail(index_data$CLOSE, 20)[1]
    price_3m <- tail(index_data$CLOSE, 60)[1]
    price_6m <- tail(index_data$CLOSE, 120)[1]
    
    perf_1m <- (current_price - price_1m) / price_1m * 100
    perf_3m <- (current_price - price_3m) / price_3m * 100
    perf_6m <- (current_price - price_6m) / price_6m * 100
    
    # Calculate relative strength vs NIFTY500
    nifty500_data <- dt_index[dt_index$SYMBOL == "Nifty 500", ]
    nifty500_data <- nifty500_data[order(nifty500_data$TIMESTAMP), ]
    nifty500_3m <- tail(nifty500_data$CLOSE, 60)[1]
    nifty500_current <- tail(nifty500_data$CLOSE, 1)
    nifty500_perf <- (nifty500_current - nifty500_3m) / nifty500_3m * 100
    
    relative_strength <- ifelse(nifty500_perf != 0, perf_3m / nifty500_perf, NA)
    
    index_row <- data.frame(
      INDEX = index,
      CURRENT_PRICE = current_price,
      PERF_1M = round(perf_1m, 2),
      PERF_3M = round(perf_3m, 2),
      PERF_6M = round(perf_6m, 2),
      RELATIVE_STRENGTH = round(relative_strength, 2),
      stringsAsFactors = FALSE
    )
    
    index_performance <- rbind(index_performance, index_row)
  }
  
  # Sort by 3M performance (only if we have data)
  if(nrow(index_performance) > 0) {
    index_performance <- index_performance[order(-index_performance$PERF_3M), ]
  }
  
  cat("Index Performance (3M):\n")
  print(index_performance)
  
  # Identify rotation trends
  cat("\nINDEX ROTATION INSIGHTS:\n")
  if(nrow(index_performance) > 0) {
    top_indices <- head(index_performance, 5)
    bottom_indices <- tail(index_performance, 5)
    
    cat("• Top 5 Performing Indices (3M):\n")
    for(i in 1:nrow(top_indices)) {
      cat("  ", i, ".", top_indices$INDEX[i], ":", top_indices$PERF_3M[i], "%\n")
    }
    
    cat("• Bottom 5 Performing Indices (3M):\n")
    for(i in 1:nrow(bottom_indices)) {
      cat("  ", i, ".", bottom_indices$INDEX[i], ":", bottom_indices$PERF_3M[i], "%\n")
    }
  } else {
    cat("• No index performance data available\n")
  }
  
  # Save long-term results
  long_term_filename <- paste0(output_dir, "long_term_screeners_", format(Sys.Date(), "%d%m%Y"), "_", 
                              format(Sys.time(), "%Y%m%d_%H%M%S"), ".csv")
  write.csv(long_term_results, long_term_filename, row.names = FALSE)
  cat("\nLong-term screener results saved to:", long_term_filename, "\n")
  
  cat("\n===============================================================================\n")
  cat("ENHANCED LONG-TERM SCREENERS SUMMARY:\n")
  cat("• Strong Monthly RS (>1.5):", nrow(strong_rs_stocks), "stocks\n")
  cat("• Consolidation Breakouts:", nrow(breakout_stocks), "stocks\n")
  cat("• Cup & Handle Patterns:", nrow(cup_handle_stocks), "stocks\n")
  cat("• Long-term Uptrends:", nrow(uptrend_stocks), "stocks\n")
  cat("• Momentum Breakouts:", nrow(momentum_stocks), "stocks\n")
  cat("• Support Bounce Patterns:", nrow(support_stocks), "stocks\n")
  cat("• Volume Accumulation:", nrow(volume_stocks), "stocks\n")
  cat("• Earnings Momentum:", nrow(earnings_stocks), "stocks\n")
  cat("• 52-Week High Breakouts:", nrow(week52_stocks), "stocks\n")
  cat("• Indices Analyzed:", nrow(index_performance), "indices\n")
  cat("===============================================================================\n")

  # Generate interactive HTML dashboard (original functionality)
  cat("\nGenerating interactive HTML dashboard...\n")
  generate_html_dashboard(results, index_results, latest_date, timestamp, output_dir)
  
  # Generate separate long-term screeners dashboard
  cat("\nGenerating long-term screeners dashboard...\n")
  source("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts/generate_long_term_screeners_dashboard.R")
  long_term_dashboard_file <- generate_long_term_screeners_dashboard(long_term_results, index_performance, latest_date, timestamp, output_dir)

  cat("\nResults saved to:", filename, "\n")
  cat("===============================================================================\n")
  print("Enhanced NSE Universe Analysis with Relative Strength Completed Successfully!")
  
} else {
  print("No results generated. Please check data quality.")
}
