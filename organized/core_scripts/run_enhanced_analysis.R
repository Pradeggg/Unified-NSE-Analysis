# =============================================================================
# ENHANCED NSE ANALYSIS - COMPLETE SYSTEM
# Runs 30-day historical data build and generates enhanced dashboard
# =============================================================================

suppressMessages({
  library(dplyr)
  library(TTR)
  library(readr)
  library(lubridate)
  library(RSQLite)
  library(DBI)
})

cat("🚀 ENHANCED NSE ANALYSIS SYSTEM\n")
cat("==============================\n\n")

# Set working directory
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')

# Database configuration
db_path <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data/nse_analysis.db'

# Create data directory if it doesn't exist
data_dir <- dirname(db_path)
if (!dir.exists(data_dir)) {
  dir.create(data_dir, recursive = TRUE)
  cat("Created data directory:", data_dir, "\n")
}

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

# Function to initialize SQLite database and create tables
initialize_database <- function(db_path) {
  cat("Initializing SQLite database...\n")
  
  # Connect to database
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Create stocks_analysis table
  stocks_table_sql <- "
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
    can_slim_score REAL,
    minervini_score REAL,
    fundamental_score REAL,
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
  index_table_sql <- "
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
  breadth_table_sql <- "
  CREATE TABLE IF NOT EXISTS market_breadth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL UNIQUE,
    total_stocks INTEGER,
    strong_buy_count INTEGER,
    buy_count INTEGER,
    hold_count INTEGER,
    weak_hold_count INTEGER,
    sell_count INTEGER,
    bullish_percentage REAL,
    bearish_percentage REAL,
    average_technical_score REAL,
    market_sentiment TEXT
  )"
  
  # Create trend_analysis table
  trend_table_sql <- "
  CREATE TABLE IF NOT EXISTS trend_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL UNIQUE,
    days_analyzed INTEGER,
    market_breadth_trends TEXT,
    index_trends TEXT,
    top_performers_trends TEXT,
    analysis_summary TEXT
  )"
  
  # Execute table creation
  dbExecute(conn, stocks_table_sql)
  dbExecute(conn, index_table_sql)
  dbExecute(conn, breadth_table_sql)
  dbExecute(conn, trend_table_sql)
  
  # Create indexes for better performance
  dbExecute(conn, "CREATE INDEX IF NOT EXISTS idx_stocks_date_symbol ON stocks_analysis(analysis_date, symbol)")
  dbExecute(conn, "CREATE INDEX IF NOT EXISTS idx_index_date_name ON index_analysis(analysis_date, index_name)")
  dbExecute(conn, "CREATE INDEX IF NOT EXISTS idx_breadth_date ON market_breadth(analysis_date)")
  dbExecute(conn, "CREATE INDEX IF NOT EXISTS idx_trend_date ON trend_analysis(analysis_date)")
  
  cat("Database initialized successfully\n")
  dbDisconnect(conn)
}

# =============================================================================
# TREND ANALYSIS FUNCTIONS
# =============================================================================

# Function to get historical data from database for trend analysis
get_historical_data_for_trends <- function(db_path, days_back = 30) {
  cat("Retrieving historical data for trend analysis...\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Get market breadth data for trend analysis
  breadth_query <- paste0("
    SELECT * FROM market_breadth 
    WHERE analysis_date >= date('now', '-", days_back, " days')
    ORDER BY analysis_date DESC
  ")
  
  breadth_data <- dbGetQuery(conn, breadth_query)
  
  # Get index analysis data
  index_query <- paste0("
    SELECT * FROM index_analysis 
    WHERE analysis_date >= date('now', '-", days_back, " days')
    ORDER BY analysis_date DESC, technical_score DESC
  ")
  
  index_data <- dbGetQuery(conn, index_query)
  
  # Get stocks analysis data for top performers
  stocks_query <- paste0("
    SELECT * FROM stocks_analysis 
    WHERE analysis_date >= date('now', '-", days_back, " days')
    AND technical_score >= 70
    ORDER BY analysis_date DESC, technical_score DESC
  ")
  
  stocks_data <- dbGetQuery(conn, index_query)
  
  dbDisconnect(conn)
  
  return(list(
    breadth = breadth_data,
    indices = index_data,
    stocks = stocks_data
  ))
}

# Function to analyze market breadth trends
analyze_market_breadth_trends <- function(breadth_data) {
  if(nrow(breadth_data) < 2) {
    return(NULL)
  }
  
  # Convert dates
  breadth_data$analysis_date <- as.Date(breadth_data$analysis_date)
  breadth_data <- breadth_data %>% arrange(analysis_date)
  
  # Calculate trends
  latest <- breadth_data[1, ]
  previous <- breadth_data[2, ]
  
  # Calculate changes
  breadth_changes <- data.frame(
    metric = c("Total Stocks", "Strong Buy Count", "Buy Count", "Hold Count", 
               "Weak Hold Count", "Sell Count", "Bullish %", "Bearish %", 
               "Average Technical Score"),
    latest_value = c(latest$total_stocks, latest$strong_buy_count, latest$buy_count,
                     latest$hold_count, latest$weak_hold_count, latest$sell_count,
                     latest$bullish_percentage, latest$bearish_percentage,
                     latest$average_technical_score),
    previous_value = c(previous$total_stocks, previous$strong_buy_count, previous$buy_count,
                       previous$hold_count, previous$weak_hold_count, previous$sell_count,
                       previous$bullish_percentage, previous$bearish_percentage,
                       previous$average_technical_score),
    stringsAsFactors = FALSE
  )
  
  breadth_changes$change <- breadth_changes$latest_value - breadth_changes$previous_value
  breadth_changes$change_pct <- round((breadth_changes$change / breadth_changes$previous_value) * 100, 2)
  
  return(breadth_changes)
}

# Function to generate comprehensive trend analysis
generate_trend_analysis <- function(db_path, days_back = 30) {
  cat("Generating comprehensive trend analysis...\n")
  
  # Get historical data
  historical_data <- get_historical_data_for_trends(db_path, days_back)
  
  if(is.null(historical_data) || nrow(historical_data$breadth) < 2) {
    cat("Insufficient historical data for trend analysis\n")
    return(NULL)
  }
  
  # Perform trend analyses
  breadth_trends <- analyze_market_breadth_trends(historical_data$breadth)
  
  # Generate report
  trend_report <- list(
    analysis_date = Sys.Date(),
    days_analyzed = days_back,
    market_breadth_trends = breadth_trends,
    historical_breadth = historical_data$breadth,
    historical_indices = historical_data$indices,
    historical_stocks = historical_data$stocks
  )
  
  return(trend_report)
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

# Initialize database
initialize_database(db_path)

# Run the main analysis script
cat("Running main NSE analysis...\n")
source('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts/fixed_nse_universe_analysis.R')

cat("\n✅ Enhanced NSE Analysis completed successfully!\n")
cat("Database updated with latest analysis results.\n")
cat("Enhanced dashboard generated with trend analysis.\n")
