# =============================================================================
# NSE TREND ANALYSIS MODULE
# Comprehensive 15-day trend analysis based on historical database data
# =============================================================================

suppressMessages({
  library(dplyr)
  library(RSQLite)
  library(DBI)
  library(ggplot2)
  library(lubridate)
})

# Database configuration
db_path <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data/nse_analysis.db'

# =============================================================================
# TREND ANALYSIS FUNCTIONS
# =============================================================================

# Function to get historical data from database
get_historical_data <- function(db_path, days_back = 15) {
  cat("Retrieving historical data from database...\n")
  
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
  
  stocks_data <- dbGetQuery(conn, stocks_query)
  
  dbDisconnect(conn)
  
  return(list(
    breadth = breadth_data,
    indices = index_data,
    stocks = stocks_data
  ))
}

# Function to analyze market breadth trends
analyze_market_breadth_trends <- function(breadth_data) {
  cat("Analyzing market breadth trends...\n")
  
  if(nrow(breadth_data) < 2) {
    cat("Insufficient data for trend analysis (need at least 2 days)\n")
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
  
  # Calculate 15-day trends
  if(nrow(breadth_data) >= 15) {
    oldest <- breadth_data[nrow(breadth_data), ]
    breadth_changes$change_15d <- breadth_changes$latest_value - oldest$total_stocks
    breadth_changes$change_15d_pct <- round((breadth_changes$change_15d / oldest$total_stocks) * 100, 2)
  } else {
    breadth_changes$change_15d <- NA
    breadth_changes$change_15d_pct <- NA
  }
  
  return(breadth_changes)
}

# Function to analyze index trends
analyze_index_trends <- function(index_data) {
  cat("Analyzing index trends...\n")
  
  if(nrow(index_data) < 2) {
    cat("Insufficient data for index trend analysis\n")
    return(NULL)
  }
  
  # Convert dates
  index_data$analysis_date <- as.Date(index_data$analysis_date)
  
  # Get latest and previous day data
  latest_date <- max(index_data$analysis_date)
  previous_date <- max(index_data$analysis_date[index_data$analysis_date < latest_date])
  
  latest_indices <- index_data[index_data$analysis_date == latest_date, ]
  previous_indices <- index_data[index_data$analysis_date == previous_date, ]
  
  # Merge data for comparison
  index_trends <- merge(
    latest_indices[, c("index_name", "technical_score", "rsi", "momentum_50d", 
                       "relative_strength", "trading_signal")],
    previous_indices[, c("index_name", "technical_score", "rsi", "momentum_50d", 
                         "relative_strength", "trading_signal")],
    by = "index_name",
    suffixes = c("_latest", "_previous")
  )
  
  # Calculate changes
  index_trends$score_change <- index_trends$technical_score_latest - index_trends$technical_score_previous
  index_trends$rsi_change <- index_trends$rsi_latest - index_trends$rsi_previous
  index_trends$momentum_change <- index_trends$momentum_50d_latest - index_trends$momentum_50d_previous
  index_trends$rs_change <- index_trends$relative_strength_latest - index_trends$relative_strength_previous
  
  # Sort by technical score change
  index_trends <- index_trends %>% arrange(desc(score_change))
  
  return(index_trends)
}

# Function to analyze top performers trends
analyze_top_performers_trends <- function(stocks_data) {
  cat("Analyzing top performers trends...\n")
  
  if(nrow(stocks_data) < 2) {
    cat("Insufficient data for top performers trend analysis\n")
    return(NULL)
  }
  
  # Convert dates
  stocks_data$analysis_date <- as.Date(stocks_data$analysis_date)
  
  # Get latest and previous day data
  latest_date <- max(stocks_data$analysis_date)
  previous_date <- max(stocks_data$analysis_date[stocks_data$analysis_date < latest_date])
  
  latest_stocks <- stocks_data[stocks_data$analysis_date == latest_date, ]
  previous_stocks <- stocks_data[stocks_data$analysis_date == previous_date, ]
  
  # Get top 20 performers from latest day
  top_20_latest <- latest_stocks %>% 
    arrange(desc(technical_score)) %>% 
    head(20)
  
  # Check which stocks were in top 20 previously
  top_20_previous <- previous_stocks %>% 
    arrange(desc(technical_score)) %>% 
    head(20)
  
  # Find new entrants and exits
  new_entrants <- setdiff(top_20_latest$symbol, top_20_previous$symbol)
  exits <- setdiff(top_20_previous$symbol, top_20_latest$symbol)
  consistent_performers <- intersect(top_20_latest$symbol, top_20_previous$symbol)
  
  # Analyze consistent performers
  consistent_analysis <- merge(
    top_20_latest[top_20_latest$symbol %in% consistent_performers, 
                  c("symbol", "technical_score", "trading_signal")],
    top_20_previous[top_20_previous$symbol %in% consistent_performers, 
                    c("symbol", "technical_score", "trading_signal")],
    by = "symbol",
    suffixes = c("_latest", "_previous")
  )
  
  consistent_analysis$score_change <- consistent_analysis$technical_score_latest - consistent_analysis$technical_score_previous
  consistent_analysis <- consistent_analysis %>% arrange(desc(score_change))
  
  return(list(
    new_entrants = new_entrants,
    exits = exits,
    consistent_performers = consistent_analysis,
    top_20_latest = top_20_latest,
    top_20_previous = top_20_previous
  ))
}

# Function to generate trend analysis report
generate_trend_analysis_report <- function(db_path, days_back = 15) {
  cat("Generating comprehensive trend analysis report...\n")
  
  # Get historical data
  historical_data <- get_historical_data(db_path, days_back)
  
  if(is.null(historical_data) || nrow(historical_data$breadth) < 2) {
    cat("Insufficient historical data for trend analysis\n")
    return(NULL)
  }
  
  # Perform trend analyses
  breadth_trends <- analyze_market_breadth_trends(historical_data$breadth)
  index_trends <- analyze_index_trends(historical_data$indices)
  top_performers_trends <- analyze_top_performers_trends(historical_data$stocks)
  
  # Generate report
  report <- list(
    analysis_date = Sys.Date(),
    days_analyzed = days_back,
    market_breadth_trends = breadth_trends,
    index_trends = index_trends,
    top_performers_trends = top_performers_trends,
    historical_breadth = historical_data$breadth
  )
  
  return(report)
}

# Function to print trend analysis summary
print_trend_analysis_summary <- function(trend_report) {
  if(is.null(trend_report)) {
    cat("No trend analysis data available\n")
    return()
  }
  
  cat("\n===============================================================================\n")
  cat("NSE MARKET TREND ANALYSIS REPORT\n")
  cat("Analysis Period:", trend_report$days_analyzed, "days ending", trend_report$analysis_date, "\n")
  cat("===============================================================================\n\n")
  
  # Market Breadth Trends
  if(!is.null(trend_report$market_breadth_trends)) {
    cat("📊 MARKET BREADTH TRENDS:\n")
    cat("========================\n")
    
    breadth_trends <- trend_report$market_breadth_trends
    
    # Key metrics
    cat("Key Market Metrics (Latest vs Previous):\n")
    for(i in 1:nrow(breadth_trends)) {
      metric <- breadth_trends[i, ]
      change_indicator <- ifelse(metric$change >= 0, "📈", "📉")
      cat(sprintf("%s %s: %.1f (%.1f%%) %s\n", 
                  change_indicator, metric$metric, metric$latest_value, 
                  metric$change_pct, ifelse(metric$change >= 0, "↗", "↘")))
    }
    cat("\n")
  }
  
  # Index Trends
  if(!is.null(trend_report$index_trends)) {
    cat("🏛️ INDEX PERFORMANCE TRENDS:\n")
    cat("============================\n")
    
    index_trends <- trend_report$index_trends
    
    cat("Top 5 Index Performers (by Technical Score Change):\n")
    top_5_indices <- head(index_trends, 5)
    for(i in 1:nrow(top_5_indices)) {
      index <- top_5_indices[i, ]
      change_indicator <- ifelse(index$score_change >= 0, "📈", "📉")
      cat(sprintf("%s %s: %.1f → %.1f (%.1f change) %s\n", 
                  change_indicator, index$index_name, 
                  index$technical_score_previous, index$technical_score_latest,
                  index$score_change, index$trading_signal_latest))
    }
    cat("\n")
  }
  
  # Top Performers Trends
  if(!is.null(trend_report$top_performers_trends)) {
    cat("🏆 TOP PERFORMERS TRENDS:\n")
    cat("=========================\n")
    
    top_trends <- trend_report$top_performers_trends
    
    cat("New Entrants to Top 20:", length(top_trends$new_entrants), "\n")
    if(length(top_trends$new_entrants) > 0) {
      cat("New Entrants:", paste(head(top_trends$new_entrants, 5), collapse = ", "), "\n")
    }
    
    cat("Exits from Top 20:", length(top_trends$exits), "\n")
    if(length(top_trends$exits) > 0) {
      cat("Exits:", paste(head(top_trends$exits, 5), collapse = ", "), "\n")
    }
    
    cat("Consistent Top Performers:", nrow(top_trends$consistent_performers), "\n")
    if(nrow(top_trends$consistent_performers) > 0) {
      cat("Top 5 Consistent Performers (by score change):\n")
      top_5_consistent <- head(top_trends$consistent_performers, 5)
      for(i in 1:nrow(top_5_consistent)) {
        stock <- top_5_consistent[i, ]
        change_indicator <- ifelse(stock$score_change >= 0, "📈", "📉")
        cat(sprintf("%s %s: %.1f → %.1f (%.1f change) %s\n", 
                    change_indicator, stock$symbol, 
                    stock$technical_score_previous, stock$technical_score_latest,
                    stock$score_change, stock$trading_signal_latest))
      }
    }
    cat("\n")
  }
  
  # Market Sentiment Summary
  if(!is.null(trend_report$historical_breadth) && nrow(trend_report$historical_breadth) > 0) {
    latest_sentiment <- trend_report$historical_breadth$market_sentiment[1]
    cat("🎯 MARKET SENTIMENT SUMMARY:\n")
    cat("============================\n")
    cat("Current Market Sentiment:", latest_sentiment, "\n")
    
    # Sentiment trend
    if(nrow(trend_report$historical_breadth) >= 3) {
      recent_sentiments <- head(trend_report$historical_breadth$market_sentiment, 3)
      sentiment_trend <- ifelse(length(unique(recent_sentiments)) == 1, "Stable", "Changing")
      cat("Sentiment Trend (3 days):", sentiment_trend, "\n")
    }
    cat("\n")
  }
  
  cat("===============================================================================\n")
}

# Function to save trend analysis to database
save_trend_analysis_to_database <- function(trend_report, db_path) {
  if(is.null(trend_report)) {
    cat("No trend analysis data to save\n")
    return()
  }
  
  cat("Saving trend analysis to database...\n")
  
  conn <- dbConnect(RSQLite::SQLite(), db_path)
  
  # Create trend_analysis table if it doesn't exist
  trend_table_sql <- "
  CREATE TABLE IF NOT EXISTS trend_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date DATE NOT NULL,
    days_analyzed INTEGER,
    analysis_type TEXT,
    metric_name TEXT,
    latest_value REAL,
    previous_value REAL,
    change_value REAL,
    change_percentage REAL,
    trend_direction TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );"
  
  dbExecute(conn, trend_table_sql)
  
  # Save market breadth trends
  if(!is.null(trend_report$market_breadth_trends)) {
    breadth_data <- trend_report$market_breadth_trends %>%
      mutate(
        analysis_date = as.character(trend_report$analysis_date),
        days_analyzed = trend_report$days_analyzed,
        analysis_type = "market_breadth",
        trend_direction = ifelse(change >= 0, "UP", "DOWN")
      ) %>%
      select(analysis_date, days_analyzed, analysis_type, metric, latest_value,
             previous_value, change, change_pct, trend_direction)
    
    colnames(breadth_data)[4] <- "metric_name"
    colnames(breadth_data)[8] <- "change_percentage"
    colnames(breadth_data)[7] <- "change_value"
    
    dbWriteTable(conn, "trend_analysis", breadth_data, append = TRUE)
  }
  
  # Save index trends
  if(!is.null(trend_report$index_trends)) {
    index_data <- trend_report$index_trends %>%
      mutate(
        analysis_date = as.character(trend_report$analysis_date),
        days_analyzed = trend_report$days_analyzed,
        analysis_type = "index_performance",
        metric_name = index_name,
        latest_value = technical_score_latest,
        previous_value = technical_score_previous,
        change_value = score_change,
        change_percentage = round((score_change / technical_score_previous) * 100, 2),
        trend_direction = ifelse(score_change >= 0, "UP", "DOWN")
      ) %>%
      select(analysis_date, days_analyzed, analysis_type, metric_name, latest_value,
             previous_value, change_value, change_percentage, trend_direction)
    
    dbWriteTable(conn, "trend_analysis", index_data, append = TRUE)
  }
  
  cat("Trend analysis saved to database\n")
  dbDisconnect(conn)
}

# =============================================================================
# MAIN TREND ANALYSIS FUNCTION
# =============================================================================

# Function to run complete trend analysis
run_trend_analysis <- function(db_path, days_back = 15, save_to_db = TRUE) {
  cat("Starting NSE Market Trend Analysis...\n")
  cat("Analysis Period:", days_back, "days\n")
  cat("Database Path:", db_path, "\n\n")
  
  # Generate trend analysis report
  trend_report <- generate_trend_analysis_report(db_path, days_back)
  
  if(!is.null(trend_report)) {
    # Print summary
    print_trend_analysis_summary(trend_report)
    
    # Save to database if requested
    if(save_to_db) {
      save_trend_analysis_to_database(trend_report, db_path)
    }
    
    return(trend_report)
  } else {
    cat("Trend analysis could not be completed due to insufficient data\n")
    return(NULL)
  }
}

# =============================================================================
# EXAMPLE USAGE
# =============================================================================

# Uncomment the following lines to run trend analysis
# trend_results <- run_trend_analysis(db_path, days_back = 15, save_to_db = TRUE)

cat("NSE Trend Analysis Module loaded successfully!\n")
cat("Use run_trend_analysis(db_path, days_back = 15) to perform trend analysis\n")
