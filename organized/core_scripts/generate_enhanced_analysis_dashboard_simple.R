# Enhanced Analysis Dashboard Generator - Simplified Version
# Multi-Timeframe & Price Action Analysis for NSE Stocks
# Author: AI Assistant
# Date: October 4, 2025

# Load required libraries
suppressMessages({
  library(DBI)
  library(RSQLite)
  library(dplyr)
  library(htmltools)
  library(jsonlite)
  library(lubridate)
})

# Set working directory
setwd("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis")

# Database connection
db_path <- "data/nse_analysis.db"
conn <- dbConnect(RSQLite::SQLite(), db_path)

# Get current date
analysis_date <- Sys.Date()

cat("🚀 Generating Enhanced Analysis Dashboard...\n")
cat("📅 Analysis Date:", as.character(analysis_date), "\n")

# Function to get stock data from database
get_stock_data <- function() {
  tryCatch({
    query <- "
    SELECT 
      symbol,
      current_price,
      change_1d,
      change_1w,
      change_1m,
      rsi,
      relative_strength,
      technical_score,
      can_slim_score,
      minervini_score,
      fundamental_score,
      trend_signal,
      trading_signal,
      market_cap_category
    FROM stocks_analysis 
    WHERE analysis_date = (
      SELECT MAX(analysis_date) FROM stocks_analysis
    )
    AND current_price > 10
    AND current_price < 20000
    ORDER BY technical_score DESC
    LIMIT 100
    "
    
    stocks_data <- dbGetQuery(conn, query)
    
    # Apply filters
    if (nrow(stocks_data) > 0) {
      stocks_data <- stocks_data %>%
        filter(
          abs(change_1d) < 15,
          abs(change_1w) < 40,
          current_price >= 25,
          current_price <= 5000,
          rsi >= 25,
          rsi <= 75,
          technical_score >= 35,
          technical_score <= 95
        )
    }
    
    return(stocks_data)
  }, error = function(e) {
    cat("❌ Error fetching stock data:", e$message, "\n")
    return(data.frame())
  })
}

# Function to generate tabular data
generate_tabular_data <- function(stocks_data) {
  cat("📊 Generating Tabular Data for Export...\n")
  
  # 1. Daily Bullish Patterns Table
  daily_bullish_table <- stocks_data %>%
    filter(!is.na(change_1d), change_1d > 0) %>%
    mutate(
      momentum = change_1d,
      pattern = case_when(
        change_1d > 15 ~ "Strong Breakout",
        change_1d > 10 ~ "Bullish Flag", 
        change_1d > 5 ~ "Ascending Triangle",
        TRUE ~ "Bullish Pennant"
      ),
      rsi_status = case_when(
        rsi > 70 ~ "Overbought",
        rsi < 30 ~ "Oversold",
        TRUE ~ "Normal"
      )
    ) %>%
    arrange(desc(change_1d)) %>%
    select(symbol, current_price, momentum, rsi, rsi_status, pattern, relative_strength, technical_score, market_cap_category)
  
  # 2. Weekly Bullish Patterns Table
  weekly_bullish_table <- stocks_data %>%
    filter(!is.na(change_1w), change_1w > 0) %>%
    mutate(
      momentum = change_1w,
      pattern = case_when(
        change_1w > 30 ~ "Strong Uptrend",
        change_1w > 15 ~ "Momentum Breakout",
        change_1w > 8 ~ "Bullish Channel",
        TRUE ~ "Support Bounce"
      ),
      rsi_status = case_when(
        rsi > 70 ~ "Overbought",
        rsi < 30 ~ "Oversold", 
        TRUE ~ "Normal"
      )
    ) %>%
    arrange(desc(change_1w)) %>%
    select(symbol, current_price, momentum, rsi, rsi_status, pattern, relative_strength, technical_score, market_cap_category)
  
  # 3. Relative Strength Leaders Table
  rs_leaders_table <- stocks_data %>%
    filter(!is.na(relative_strength)) %>%
    mutate(
      rs_category = case_when(
        relative_strength > 50 ~ "Exceptional",
        relative_strength > 20 ~ "Very Strong",
        relative_strength > 10 ~ "Strong",
        relative_strength > 5 ~ "Moderate",
        TRUE ~ "Weak"
      ),
      rs_strength = case_when(
        relative_strength > 20 ~ "Strong",
        relative_strength > 10 ~ "Medium",
        TRUE ~ "Weak"
      )
    ) %>%
    arrange(desc(relative_strength)) %>%
    select(symbol, current_price, relative_strength, rs_category, rs_strength, technical_score, rsi, change_1d, change_1w, market_cap_category)
  
  # 4. Top Technical Scores Table
  top_technical_table <- stocks_data %>%
    filter(!is.na(technical_score)) %>%
    mutate(
      risk_level = case_when(
        rsi > 70 | rsi < 30 ~ "High",
        rsi > 60 | rsi < 40 ~ "Medium",
        TRUE ~ "Low"
      ),
      investment_horizon = case_when(
        technical_score > 75 & relative_strength > 1.5 ~ "Short-term (1-3 months)",
        technical_score > 60 & relative_strength > 1.2 ~ "Medium-term (3-6 months)",
        technical_score > 45 & relative_strength > 1.0 ~ "Long-term (6+ months)",
        TRUE ~ "Watch List"
      )
    ) %>%
    arrange(desc(technical_score)) %>%
    select(symbol, current_price, technical_score, relative_strength, rsi, risk_level, investment_horizon, change_1d, change_1w, market_cap_category)
  
  # 5. Market Cap Analysis Table
  market_cap_analysis <- stocks_data %>%
    filter(!is.na(relative_strength)) %>%
    group_by(market_cap_category) %>%
    summarise(
      stock_count = n(),
      avg_technical_score = round(mean(technical_score, na.rm = TRUE), 2),
      avg_relative_strength = round(mean(relative_strength, na.rm = TRUE), 2),
      avg_rsi = round(mean(rsi, na.rm = TRUE), 2),
      avg_change_1d = round(mean(change_1d, na.rm = TRUE), 2),
      avg_change_1w = round(mean(change_1w, na.rm = TRUE), 2),
      .groups = 'drop'
    ) %>%
    mutate(
      recommendation = case_when(
        avg_relative_strength > 1.3 & avg_technical_score > 60 ~ "Strong Buy",
        avg_relative_strength > 1.1 & avg_technical_score > 50 ~ "Buy",
        avg_relative_strength > 0.9 & avg_technical_score > 40 ~ "Hold",
        TRUE ~ "Avoid"
      )
    ) %>%
    arrange(desc(avg_technical_score))
  
  # 6. Risk Management Table
  risk_management_table <- stocks_data %>%
    filter(!is.na(technical_score), !is.na(rsi)) %>%
    mutate(
      risk_category = case_when(
        technical_score > 70 & rsi > 50 & rsi < 70 ~ "Low Risk",
        technical_score > 50 & rsi > 40 & rsi < 80 ~ "Medium Risk",
        TRUE ~ "High Risk"
      )
    ) %>%
    group_by(risk_category) %>%
    summarise(
      stock_count = n(),
      avg_technical_score = round(mean(technical_score, na.rm = TRUE), 2),
      avg_relative_strength = round(mean(relative_strength, na.rm = TRUE), 2),
      avg_rsi = round(mean(rsi, na.rm = TRUE), 2),
      .groups = 'drop'
    ) %>%
    arrange(desc(avg_technical_score))
  
  return(list(
    dailyBullish = daily_bullish_table,
    weeklyBullish = weekly_bullish_table,
    rsLeaders = rs_leaders_table,
    topTechnical = top_technical_table,
    marketCapAnalysis = market_cap_analysis,
    riskManagement = risk_management_table
  ))
}

# Function to save data as CSV files
save_tabular_data <- function(tabular_data) {
  cat("💾 Saving Tabular Data as CSV Files...\n")
  
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Save each table as CSV
  write.csv(tabular_data$dailyBullish, 
            file = paste0("reports/Daily_Bullish_Patterns_", timestamp, ".csv"), 
            row.names = FALSE)
  
  write.csv(tabular_data$weeklyBullish, 
            file = paste0("reports/Weekly_Bullish_Patterns_", timestamp, ".csv"), 
            row.names = FALSE)
  
  write.csv(tabular_data$rsLeaders, 
            file = paste0("reports/Relative_Strength_Leaders_", timestamp, ".csv"), 
            row.names = FALSE)
  
  write.csv(tabular_data$topTechnical, 
            file = paste0("reports/Top_Technical_Scores_", timestamp, ".csv"), 
            row.names = FALSE)
  
  write.csv(tabular_data$marketCapAnalysis, 
            file = paste0("reports/Market_Cap_Analysis_", timestamp, ".csv"), 
            row.names = FALSE)
  
  write.csv(tabular_data$riskManagement, 
            file = paste0("reports/Risk_Management_", timestamp, ".csv"), 
            row.names = FALSE)
  
  cat("✅ All CSV files saved successfully!\n")
}

# Function to display tabular data in console
display_tabular_data <- function(tabular_data) {
  cat("\n📊 ENHANCED ANALYSIS DASHBOARD - TABULAR RESULTS\n")
  cat("================================================\n\n")
  
  # 1. Daily Bullish Patterns
  cat("📈 DAILY BULLISH PATTERNS (Top 10):\n")
  cat("====================================\n")
  print(head(tabular_data$dailyBullish, 10))
  
  cat("\n📅 WEEKLY BULLISH PATTERNS (Top 10):\n")
  cat("======================================\n")
  print(head(tabular_data$weeklyBullish, 10))
  
  cat("\n💪 RELATIVE STRENGTH LEADERS (Top 15):\n")
  cat("========================================\n")
  print(head(tabular_data$rsLeaders, 15))
  
  cat("\n🏆 TOP TECHNICAL SCORES (Top 15):\n")
  cat("==================================\n")
  print(head(tabular_data$topTechnical, 15))
  
  cat("\n🏢 MARKET CAP ANALYSIS:\n")
  cat("========================\n")
  print(tabular_data$marketCapAnalysis)
  
  cat("\n🛡️ RISK MANAGEMENT ANALYSIS:\n")
  cat("=============================\n")
  print(tabular_data$riskManagement)
}

# Main execution
tryCatch({
  cat("📊 Starting Enhanced Analysis Dashboard Generation...\n")
  
  # Get stock data
  stocks_data <- get_stock_data()
  
  if (nrow(stocks_data) == 0) {
    cat("❌ No stock data found in database\n")
    stop("No data available")
  }
  
  cat("✅ Found", nrow(stocks_data), "stocks in database\n")
  
  # Generate tabular data
  tabular_data <- generate_tabular_data(stocks_data)
  
  # Display results
  display_tabular_data(tabular_data)
  
  # Save CSV files
  save_tabular_data(tabular_data)
  
  cat("\n🎉 Enhanced Analysis Dashboard generation completed!\n")
  cat("📁 CSV files saved in reports/ directory\n")
  
}, error = function(e) {
  cat("❌ Error generating dashboard:", e$message, "\n")
}, finally = {
  # Close database connection
  if (exists("conn")) {
    dbDisconnect(conn)
  }
})

cat("🎉 Enhanced Analysis Dashboard generation completed!\n")

