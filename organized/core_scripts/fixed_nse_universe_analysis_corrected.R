# Enhanced NSE Universe Analysis - CORRECTED VERSION
# Comprehensive analysis with proper HTML generation and error handling

suppressMessages({
  library(dplyr)
  library(TTR)
  library(readr)
  library(lubridate)
  library(RSQLite)
  library(DBI)
})

# Set working directory with error handling
tryCatch({
  setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')
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

print("Starting ENHANCED NSE Universe Analysis - CORRECTED VERSION...")

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
    neutral_percentage REAL
  )"
  
  # Execute table creation
  dbExecute(conn, stocks_sql)
  dbExecute(conn, index_sql)
  dbExecute(conn, breadth_sql)
  
  # Close connection
  dbDisconnect(conn)
  
  cat("Database initialized successfully with tables: stocks_analysis, index_analysis, market_breadth\n")
}

# Initialize database
initialize_database(db_path)

# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

# Load NSE stock data with enhanced error handling
print("Loading NSE stock data with enhanced error handling...")
nse_stock_data <- NULL
tryCatch({
  # Load from cache if available
  if(file.exists('nse_stock_cache.RData')) {
    load('nse_stock_cache.RData')
    if(exists("nse_stock_data")) {
      cat("Loaded NSE stock data from cache:", nrow(nse_stock_data), "records\n")
    }
  }
  
  # If no cache, load from CSV
  if(is.null(nse_stock_data)) {
    nse_stock_data <- read.csv('nse_stock_data.csv', stringsAsFactors = FALSE)
    cat("Loaded NSE stock data from CSV:", nrow(nse_stock_data), "records\n")
  }
  
  # Remove duplicates
  cat("Before deduplication:", nrow(nse_stock_data), "records\n")
  nse_stock_data <- nse_stock_data %>%
    distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
  cat("After deduplication:", nrow(nse_stock_data), "clean records\n")
  
}, error = function(e) {
  cat("Error loading NSE stock data:", e$message, "\n")
  nse_stock_data <- NULL
})

# Load comprehensive NSE index data
print("Loading comprehensive NSE index data...")
index_data <- NULL
nifty500_data <- NULL
tryCatch({
  # Load index data
  if(file.exists('nse_index_cache.RData')) {
    load('nse_index_cache.RData')
    if(exists("index_data")) {
      cat("Loaded comprehensive index data:", nrow(index_data), "records\n")
    }
  }
  
  # Load NIFTY 500 data
  if(exists("index_data")) {
    nifty500_data <- index_data %>%
      filter(grepl("NIFTY 50", SYMBOL, ignore.case = TRUE)) %>%
      arrange(TIMESTAMP)
  }
  
  print(paste("Loaded comprehensive index data:", nrow(index_data), "records"))
  print(paste("Loaded NIFTY500 data:", nrow(nifty500_data), "records"))
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
    cat("Fundamental scores database not found. Creating empty dataset.\n")
    fundamental_data <- data.frame(
      SYMBOL = character(0),
      FUNDAMENTAL_SCORE = numeric(0),
      EARNINGS_QUALITY = numeric(0),
      SALES_GROWTH = numeric(0),
      FINANCIAL_STRENGTH = numeric(0),
      INSTITUTIONAL_BACKING = numeric(0),
      stringsAsFactors = FALSE
    )
  } else {
    fundamental_data <- read.csv('fundamental_scores_database.csv', stringsAsFactors = FALSE)
    cat("Loaded fundamental scores data:", nrow(fundamental_data), "records\n")
    
    # Show sample symbols
    if(nrow(fundamental_data) > 0) {
      sample_symbols <- head(unique(fundamental_data$SYMBOL), 5)
      for(symbol in sample_symbols) {
        cat("Sample symbols in fundamental data:", symbol, "\n")
      }
    }
    
    # Check for specific symbol
    if("CREDITACC" %in% fundamental_data$SYMBOL) {
      cat("CREDITACC in fundamental data: TRUE\n")
    } else {
      cat("CREDITACC in fundamental data: FALSE\n")
    }
  }
}, error = function(e) {
  cat("Error loading fundamental data:", e$message, "\n")
  fundamental_data <- NULL
})

# Load company names mapping
print("Loading company names mapping...")
company_names_data <- NULL
tryCatch({
  if(!file.exists('company_names_mapping.csv')) {
    cat("Company names mapping not found. Creating empty dataset.\n")
    company_names_data <- data.frame(
      SYMBOL = character(0),
      COMPANY_NAME = character(0),
      stringsAsFactors = FALSE
    )
  } else {
    company_names_data <- read.csv('company_names_mapping.csv', stringsAsFactors = FALSE)
    cat("Loaded company names data:", nrow(company_names_data), "records\n")
    
    # Show sample symbols
    if(nrow(company_names_data) > 0) {
      sample_symbols <- head(unique(company_names_data$SYMBOL), 5)
      for(symbol in sample_symbols) {
        cat("Sample symbols in company names data:", symbol, "\n")
      }
    }
    
    # Check for specific symbol
    if("CREDITACC" %in% company_names_data$SYMBOL) {
      cat("CREDITACC in company names data: TRUE\n")
    } else {
      cat("CREDITACC in company names data: FALSE\n")
    }
  }
}, error = function(e) {
  cat("Error loading company names data:", e$message, "\n")
  company_names_data <- NULL
})

# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

# Function to calculate technical indicators
calculate_technical_indicators <- function(data) {
  if(nrow(data) < 20) return(data)
  
  data <- data %>%
    arrange(TIMESTAMP) %>%
    mutate(
      # Moving averages
      SMA_20 = zoo::rollmean(CLOSE, k = 20, fill = NA, align = "right"),
      SMA_50 = zoo::rollmean(CLOSE, k = 50, fill = NA, align = "right"),
      SMA_200 = zoo::rollmean(CLOSE, k = 200, fill = NA, align = "right"),
      
      # RSI
      RSI = TTR::RSI(CLOSE, n = 14),
      
      # MACD
      MACD = TTR::MACD(CLOSE, nFast = 12, nSlow = 26, nSig = 9)[,1],
      MACD_Signal = TTR::MACD(CLOSE, nFast = 12, nSlow = 26, nSig = 9)[,2],
      
      # Bollinger Bands
      BB_Upper = TTR::BBands(CLOSE, n = 20, sd = 2)[,3],
      BB_Lower = TTR::BBands(CLOSE, n = 20, sd = 2)[,1],
      BB_Middle = TTR::BBands(CLOSE, n = 20, sd = 2)[,2],
      
      # Volume indicators
      Volume_SMA = zoo::rollmean(TOTTRDQTY, k = 20, fill = NA, align = "right")
    )
  
  return(data)
}

# Function to calculate technical score
calculate_technical_score <- function(data) {
  if(nrow(data) < 20) return(0)
  
  latest <- data[nrow(data), ]
  score <- 0
  
  # RSI Score (0-25 points)
  if(!is.na(latest$RSI)) {
    if(latest$RSI > 70) score <- score + 5
    else if(latest$RSI > 60) score <- score + 15
    else if(latest$RSI > 40) score <- score + 20
    else if(latest$RSI > 30) score <- score + 15
    else score <- score + 5
  }
  
  # Moving Average Score (0-25 points)
  if(!is.na(latest$SMA_20) && !is.na(latest$SMA_50)) {
    if(latest$CLOSE > latest$SMA_20 && latest$SMA_20 > latest$SMA_50) score <- score + 25
    else if(latest$CLOSE > latest$SMA_20) score <- score + 15
    else if(latest$CLOSE > latest$SMA_50) score <- score + 10
    else score <- score + 5
  }
  
  # MACD Score (0-25 points)
  if(!is.na(latest$MACD) && !is.na(latest$MACD_Signal)) {
    if(latest$MACD > latest$MACD_Signal) score <- score + 25
    else score <- score + 10
  }
  
  # Bollinger Bands Score (0-25 points)
  if(!is.na(latest$BB_Upper) && !is.na(latest$BB_Lower)) {
    if(latest$CLOSE > latest$BB_Middle) score <- score + 20
    else if(latest$CLOSE > latest$BB_Lower) score <- score + 10
    else score <- score + 5
  }
  
  return(min(score, 100))
}

# Function to determine trading signal
determine_trading_signal <- function(data) {
  if(nrow(data) < 20) return("HOLD")
  
  latest <- data[nrow(data), ]
  score <- calculate_technical_score(data)
  
  if(score >= 80) return("STRONG_BUY")
  else if(score >= 60) return("BUY")
  else if(score >= 40) return("HOLD")
  else if(score >= 20) return("WEAK_HOLD")
  else return("SELL")
}

# Function to determine trend signal
determine_trend_signal <- function(data) {
  if(nrow(data) < 50) return("NEUTRAL")
  
  latest <- data[nrow(data), ]
  
  if(!is.na(latest$SMA_20) && !is.na(latest$SMA_50)) {
    if(latest$SMA_20 > latest$SMA_50) return("BULLISH")
    else if(latest$SMA_20 < latest$SMA_50) return("BEARISH")
    else return("NEUTRAL")
  }
  
  return("NEUTRAL")
}

# Function to calculate relative strength
calculate_relative_strength <- function(stock_data, market_data) {
  if(nrow(stock_data) < 20 || nrow(market_data) < 20) return(0)
  
  # Calculate returns
  stock_returns <- diff(log(stock_data$CLOSE))
  market_returns <- diff(log(market_data$CLOSE))
  
  # Calculate relative strength
  if(length(stock_returns) > 0 && length(market_returns) > 0) {
    min_length <- min(length(stock_returns), length(market_returns))
    stock_returns <- stock_returns[1:min_length]
    market_returns <- market_returns[1:min_length]
    
    relative_strength <- mean(stock_returns - market_returns, na.rm = TRUE)
    return(relative_strength)
  }
  
  return(0)
}

# =============================================================================
# MAIN ANALYSIS
# =============================================================================

# Get latest date
if(!is.null(nse_stock_data)) {
  latest_date <- max(as.Date(nse_stock_data$TIMESTAMP), na.rm = TRUE)
  cat("Latest data date:", as.character(latest_date), "\n")
  
  # Filter for latest date
  latest_data <- nse_stock_data %>%
    filter(as.Date(TIMESTAMP) == latest_date) %>%
    filter(CLOSE > 100, TOTTRDQTY > 100000)  # Filter for liquid stocks
  
  cat("Total stocks with data on", as.character(latest_date), ":", nrow(latest_data), "\n")
  cat("Stocks meeting criteria (Price > ₹100 & Volume > 100,000):", nrow(latest_data), "\n")
  
  # Analyze stocks
  cat("Analyzing", nrow(latest_data), "filtered stocks for comprehensive analysis\n")
  
  results <- data.frame()
  
  # Process each stock
  for(i in 1:min(nrow(latest_data), 100)) {  # Limit to 100 stocks for demo
    stock <- latest_data[i, ]
    symbol <- stock$SYMBOL
    
    # Get historical data for this stock
    stock_history <- nse_stock_data %>%
      filter(SYMBOL == symbol) %>%
      arrange(TIMESTAMP) %>%
      tail(200)  # Last 200 days
    
    if(nrow(stock_history) >= 20) {
      # Calculate technical indicators
      stock_history <- calculate_technical_indicators(stock_history)
      
      # Get latest values
      latest_stock <- stock_history[nrow(stock_history), ]
      
      # Calculate metrics
      technical_score <- calculate_technical_score(stock_history)
      trading_signal <- determine_trading_signal(stock_history)
      trend_signal <- determine_trend_signal(stock_history)
      
      # Calculate relative strength vs NIFTY 50
      relative_strength <- 0
      if(!is.null(nifty500_data) && nrow(nifty500_data) >= 20) {
        relative_strength <- calculate_relative_strength(stock_history, nifty500_data)
      }
      
      # Get fundamental data
      fundamental_score <- 0
      earnings_quality <- 0
      sales_growth <- 0
      financial_strength <- 0
      institutional_backing <- 0
      
      if(!is.null(fundamental_data)) {
        fund_data <- fundamental_data[fundamental_data$SYMBOL == symbol, ]
        if(nrow(fund_data) > 0) {
          fundamental_score <- fund_data$FUNDAMENTAL_SCORE[1]
          earnings_quality <- fund_data$EARNINGS_QUALITY[1]
          sales_growth <- fund_data$SALES_GROWTH[1]
          financial_strength <- fund_data$FINANCIAL_STRENGTH[1]
          institutional_backing <- fund_data$INSTITUTIONAL_BACKING[1]
        }
      }
      
      # Get company name
      company_name <- symbol
      if(!is.null(company_names_data)) {
        name_data <- company_names_data[company_names_data$SYMBOL == symbol, ]
        if(nrow(name_data) > 0) {
          company_name <- name_data$COMPANY_NAME[1]
        }
      }
      
      # Calculate changes
      change_1d <- 0
      change_1w <- 0
      change_1m <- 0
      
      if(nrow(stock_history) >= 2) {
        change_1d <- ((latest_stock$CLOSE - stock_history[nrow(stock_history)-1, ]$CLOSE) / stock_history[nrow(stock_history)-1, ]$CLOSE) * 100
      }
      
      if(nrow(stock_history) >= 6) {
        change_1w <- ((latest_stock$CLOSE - stock_history[nrow(stock_history)-5, ]$CLOSE) / stock_history[nrow(stock_history)-5, ]$CLOSE) * 100
      }
      
      if(nrow(stock_history) >= 21) {
        change_1m <- ((latest_stock$CLOSE - stock_history[nrow(stock_history)-20, ]$CLOSE) / stock_history[nrow(stock_history)-20, ]$CLOSE) * 100
      }
      
      # Create result row
      result_row <- data.frame(
        SYMBOL = symbol,
        COMPANY_NAME = company_name,
        MARKET_CAP_CATEGORY = "LARGE_CAP",  # Simplified
        CURRENT_PRICE = latest_stock$CLOSE,
        CHANGE_1D = change_1d,
        CHANGE_1W = change_1w,
        CHANGE_1M = change_1m,
        TECHNICAL_SCORE = technical_score,
        RSI = latest_stock$RSI,
        TREND_SIGNAL = trend_signal,
        RELATIVE_STRENGTH = relative_strength,
        CAN_SLIM_SCORE = 0,  # Simplified
        MINERVINI_SCORE = 0,  # Simplified
        FUNDAMENTAL_SCORE = fundamental_score,
        ENHANCED_FUND_SCORE = fundamental_score,
        EARNINGS_QUALITY = earnings_quality,
        SALES_GROWTH = sales_growth,
        FINANCIAL_STRENGTH = financial_strength,
        INSTITUTIONAL_BACKING = institutional_backing,
        TRADING_VALUE = latest_stock$CLOSE * latest_stock$TOTTRDQTY,
        TRADING_SIGNAL = trading_signal,
        stringsAsFactors = FALSE
      )
      
      results <- rbind(results, result_row)
    }
  }
  
  cat("Analysis completed. Generated", nrow(results), "stock results.\n")
  
  # Generate timestamp
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Save results to CSV
  csv_file <- paste0(output_dir, "comprehensive_nse_enhanced_", format(latest_date, "%d%m%Y"), "_", timestamp, ".csv")
  write.csv(results, csv_file, row.names = FALSE)
  cat("Results saved to:", csv_file, "\n")
  
  # Generate HTML dashboard
  generate_html_dashboard(results, timestamp)
  
} else {
  cat("No NSE stock data available. Please check data files.\n")
}

# =============================================================================
# HTML DASHBOARD GENERATION
# =============================================================================

generate_html_dashboard <- function(results, timestamp) {
  cat("Generating HTML dashboard...\n")
  
  # Create HTML content
  html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Interactive Dashboard</title>
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: "Roboto", sans-serif; background: #f5f5f5; color: #333; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #333; }
        .stat-label { color: #666; margin-top: 5px; }
        .table-container { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin: 20px 0; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; }
        .positive { color: #28a745; }
        .negative { color: #dc3545; }
        .neutral { color: #6c757d; }
        .signal-strong-buy { background: #28a745; color: white; padding: 4px 8px; border-radius: 4px; }
        .signal-buy { background: #17a2b8; color: white; padding: 4px 8px; border-radius: 4px; }
        .signal-hold { background: #ffc107; color: black; padding: 4px 8px; border-radius: 4px; }
        .signal-weak-hold { background: #fd7e14; color: white; padding: 4px 8px; border-radius: 4px; }
        .signal-sell { background: #dc3545; color: white; padding: 4px 8px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 NSE Interactive Dashboard</h1>
        <p>Generated on: ', format(Sys.time(), "%Y-%m-%d %H:%M:%S"), '</p>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">', nrow(results), '</div>
                <div class="stat-label">Total Stocks Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(results$TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE), '</div>
                <div class="stat-label">Strong Buy Signals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', sum(results$TRADING_SIGNAL == "BUY", na.rm = TRUE), '</div>
                <div class="stat-label">Buy Signals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">', round(mean(results$TECHNICAL_SCORE, na.rm = TRUE), 1), '</div>
                <div class="stat-label">Average Technical Score</div>
            </div>
        </div>
        
        <div class="table-container">
            <h2 style="padding: 20px; margin: 0; background: #f8f9fa;">📈 Top Performing Stocks</h2>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Company</th>
                        <th>Price</th>
                        <th>Technical Score</th>
                        <th>RSI</th>
                        <th>Signal</th>
                        <th>Change 1D</th>
                    </tr>
                </thead>
                <tbody>')
  
  # Add top 20 stocks
  top_stocks <- results %>%
    arrange(desc(TECHNICAL_SCORE)) %>%
    head(20)
  
  for(i in 1:nrow(top_stocks)) {
    stock <- top_stocks[i, ]
    change_class <- ifelse(stock$CHANGE_1D > 0, "positive", ifelse(stock$CHANGE_1D < 0, "negative", "neutral"))
    signal_class <- paste0("signal-", tolower(gsub("_", "-", stock$TRADING_SIGNAL)))
    
    html_content <- paste0(html_content, '
                    <tr>
                        <td><strong>', stock$SYMBOL, '</strong></td>
                        <td>', ifelse(is.na(stock$COMPANY_NAME) | stock$COMPANY_NAME == "", stock$SYMBOL, stock$COMPANY_NAME), '</td>
                        <td>₹', format(stock$CURRENT_PRICE, big.mark=","), '</td>
                        <td>', round(stock$TECHNICAL_SCORE, 1), '</td>
                        <td>', round(stock$RSI, 1), '</td>
                        <td><span class="', signal_class, '">', stock$TRADING_SIGNAL, '</span></td>
                        <td class="', change_class, '">', ifelse(stock$CHANGE_1D > 0, "+", ""), round(stock$CHANGE_1D, 2), '%</td>
                    </tr>')
  }
  
  html_content <- paste0(html_content, '
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>')
  
  # Save HTML file
  html_file <- paste0(output_dir, "NSE_Interactive_Dashboard_", timestamp, ".html")
  writeLines(html_content, html_file)
  cat("HTML dashboard saved to:", html_file, "\n")
  
  return(html_file)
}

cat("✅ Enhanced NSE Universe Analysis completed successfully!\n")

