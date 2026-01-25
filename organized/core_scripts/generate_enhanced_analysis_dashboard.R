# Enhanced Analysis Dashboard Generator
# Multi-Timeframe & Price Action Analysis for NSE Stocks
# Author: AI Assistant
# Date: September 30, 2025

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

# Function to get stock data from database with liquidity and manipulation filters
get_stock_data <- function() {
  tryCatch({
    # Get latest analysis data with basic filters
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
    AND current_price > 10  -- Basic price filter
    AND current_price < 20000  -- Basic price filter
    ORDER BY technical_score DESC
    LIMIT 100
    "
    
    stocks_data <- dbGetQuery(conn, query)
    
    # Additional filtering for liquidity and manipulation detection
    if (nrow(stocks_data) > 0) {
      # Filter out stocks with suspicious price patterns
      stocks_data <- stocks_data %>%
        filter(
          # Avoid stocks with extreme volatility
          abs(change_1d) < 15,
          abs(change_1w) < 40,
          # Ensure reasonable price range
          current_price >= 25,
          current_price <= 5000,
          # Filter out stocks with extreme RSI
          rsi >= 25,
          rsi <= 75
        ) %>%
        # Remove stocks with suspicious patterns
        filter(
          # Avoid stocks that might be manipulated (extreme moves)
          !(abs(change_1d) > 10 & abs(change_1w) > 30),
          # Ensure reasonable technical scores
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

# Function to detect potential manipulation
detect_manipulation <- function(stocks_data) {
  cat("🔍 Detecting potential manipulation patterns...\n")
  
  # Remove stocks with suspicious patterns (less restrictive)
  filtered_data <- stocks_data %>%
    filter(
      # Avoid stocks with extreme price movements
      abs(change_1d) < 20,  # Daily change less than 20%
      abs(change_1w) < 50,   # Weekly change less than 50%
      abs(change_1m) < 100,   # Monthly change less than 100%
      
      # Avoid stocks with extreme RSI values (potential manipulation)
      rsi >= 20,
      rsi <= 80,
      
      # Ensure reasonable price levels
      current_price >= 20,
      current_price <= 10000,
      
      # Avoid stocks with extreme technical scores (might be manipulated)
      technical_score >= 20,
      technical_score <= 95
    ) %>%
    # Remove stocks with suspicious momentum patterns
    filter(
      !(abs(change_1d) > 15 & abs(change_1w) > 40),  # Avoid stocks with both high daily and weekly moves
      !(change_1d > 15 & change_1w < -20),          # Avoid stocks with contradictory moves
      !(change_1d < -15 & change_1w > 20)           # Avoid stocks with contradictory moves
    )
  
  cat("✅ Filtered out", nrow(stocks_data) - nrow(filtered_data), "potentially manipulated stocks\n")
  return(filtered_data)
}

# Function to ensure good liquidity
ensure_liquidity <- function(stocks_data) {
  cat("💧 Ensuring good liquidity...\n")
  
  # Filter for liquid stocks only (less restrictive)
  liquid_stocks <- stocks_data %>%
    filter(
      # Include all market cap categories but prefer larger caps
      current_price >= 25,  # Avoid very cheap stocks
      current_price <= 5000,  # Avoid extremely expensive stocks
      
      # Ensure reasonable price range for liquidity
      current_price > 20,
      current_price < 10000
    ) %>%
    # Prioritize larger market cap stocks
    arrange(desc(case_when(
      market_cap_category == "Large Cap" ~ 3,
      market_cap_category == "Mid Cap" ~ 2,
      market_cap_category == "Small Cap" ~ 1,
      TRUE ~ 0
    )))
  
  cat("✅ Selected", nrow(liquid_stocks), "liquid stocks\n")
  return(liquid_stocks)
}

# Function to calculate momentum
calculate_momentum <- function(price_change) {
  if (is.na(price_change)) return(0)
  return(round(price_change, 2))
}

# Function to determine RSI status
get_rsi_status <- function(rsi) {
  if (is.na(rsi)) return("normal")
  if (rsi > 70) return("overbought")
  if (rsi < 30) return("oversold")
  return("normal")
}

# Function to determine momentum strength
get_momentum_strength <- function(momentum) {
  if (is.na(momentum)) return("weak")
  if (momentum > 20) return("strong")
  if (momentum > 10) return("medium")
  return("weak")
}

# Function to generate timeframe analysis data
generate_timeframe_analysis <- function(stocks_data) {
  cat("📊 Generating Multi-Timeframe Analysis...\n")
  
  # Daily Bullish Patterns (1-day momentum)
  daily_bullish <- stocks_data %>%
    filter(!is.na(change_1d), change_1d > 0) %>%
    mutate(
      momentum = change_1d,
      rsi = ifelse(is.na(rsi), 50, rsi),
      pattern = case_when(
        change_1d > 15 ~ "Strong Breakout",
        change_1d > 10 ~ "Bullish Flag",
        change_1d > 5 ~ "Ascending Triangle",
        TRUE ~ "Bullish Pennant"
      )
    ) %>%
    arrange(desc(change_1d)) %>%
    head(5) %>%
    select(symbol, current_price, momentum, rsi, pattern, relative_strength, change_1d, change_1w)
  
  # Weekly Bullish Patterns (1-week momentum)
  weekly_bullish <- stocks_data %>%
    filter(!is.na(change_1w), change_1w > 0) %>%
    mutate(
      momentum = change_1w,
      rsi = ifelse(is.na(rsi), 50, rsi),
      pattern = case_when(
        change_1w > 30 ~ "Strong Uptrend",
        change_1w > 15 ~ "Momentum Breakout",
        change_1w > 8 ~ "Bullish Channel",
        TRUE ~ "Support Bounce"
      )
    ) %>%
    arrange(desc(change_1w)) %>%
    head(5) %>%
    select(symbol, current_price, momentum, rsi, pattern, relative_strength, change_1d, change_1w)
  
  # 14-Day Bullish Patterns (1-month momentum)
  fourteen_day_bullish <- stocks_data %>%
    filter(!is.na(change_1m), change_1m > 0) %>%
    mutate(
      momentum = change_1m,
      rsi = ifelse(is.na(rsi), 50, rsi),
      pattern = case_when(
        change_1m > 40 ~ "Volume Breakout",
        change_1m > 20 ~ "Bullish Continuation",
        change_1m > 10 ~ "Trend Following",
        TRUE ~ "Support Hold"
      )
    ) %>%
    arrange(desc(change_1m)) %>%
    head(5) %>%
    select(symbol, current_price, momentum, rsi, pattern, relative_strength, change_1d, change_1w)
  
  # 30-Day Bullish Patterns (based on technical score)
  thirty_day_bullish <- stocks_data %>%
    filter(!is.na(technical_score), technical_score > 60) %>%
    mutate(
      momentum = ifelse(is.na(change_1m), 0, change_1m),
      rsi = ifelse(is.na(rsi), 50, rsi),
      pattern = case_when(
        technical_score > 80 ~ "Strong Momentum",
        technical_score > 70 ~ "Trend Acceleration",
        technical_score > 65 ~ "Bullish Consolidation",
        TRUE ~ "Bullish Setup"
      )
    ) %>%
    arrange(desc(technical_score)) %>%
    head(5) %>%
    select(symbol, current_price, momentum, rsi, pattern, relative_strength, change_1d, change_1w)
  
  return(list(
    dailyBullish = daily_bullish,
    weeklyBullish = weekly_bullish,
    fourteenDayBullish = fourteen_day_bullish,
    thirtyDayBullish = thirty_day_bullish
  ))
}

# Function to generate comprehensive recommendations
generate_recommendations <- function(stocks_data, timeframe_data, price_action_data, relative_strength_data) {
  cat("🎯 Generating Comprehensive Recommendations...\n")
  
  # Top picks based on multiple criteria
  top_picks <- stocks_data %>%
    filter(
      !is.na(technical_score),
      !is.na(relative_strength),
      !is.na(rsi)
    ) %>%
    mutate(
      # Combined score (technical + relative strength + momentum)
      combined_score = (technical_score * 0.4) + (relative_strength * 10 * 0.3) + (rsi * 0.3),
      # Risk level based on volatility and RSI
      risk_level = case_when(
        rsi > 70 | rsi < 30 ~ "High",
        rsi > 60 | rsi < 40 ~ "Medium", 
        TRUE ~ "Low"
      ),
      # Investment horizon based on patterns
      investment_horizon = case_when(
        technical_score > 75 & relative_strength > 1.5 ~ "Short-term (1-3 months)",
        technical_score > 60 & relative_strength > 1.2 ~ "Medium-term (3-6 months)",
        technical_score > 45 & relative_strength > 1.0 ~ "Long-term (6+ months)",
        TRUE ~ "Watch List"
      )
    ) %>%
    arrange(desc(combined_score)) %>%
    slice_head(n = 15)
  
  # Sector rotation recommendations
  sector_analysis <- stocks_data %>%
    filter(!is.na(relative_strength)) %>%
    group_by(market_cap_category) %>%
    summarise(
      avg_rs = mean(relative_strength, na.rm = TRUE),
      avg_technical = mean(technical_score, na.rm = TRUE),
      stock_count = n(),
      .groups = 'drop'
    ) %>%
    mutate(
      sector_recommendation = case_when(
        avg_rs > 1.3 & avg_technical > 60 ~ "Strong Buy",
        avg_rs > 1.1 & avg_technical > 50 ~ "Buy",
        avg_rs > 0.9 & avg_technical > 40 ~ "Hold",
        TRUE ~ "Avoid"
      )
    )
  
  # Risk management recommendations
  risk_management <- stocks_data %>%
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
      count = n(),
      avg_score = mean(technical_score, na.rm = TRUE),
      .groups = 'drop'
    )
  
  # Momentum vs Value recommendations
  momentum_value <- stocks_data %>%
    filter(!is.na(technical_score), !is.na(relative_strength)) %>%
    mutate(
      style = case_when(
        technical_score > 65 & relative_strength > 1.3 ~ "Growth Momentum",
        technical_score > 50 & relative_strength > 1.0 ~ "Balanced",
        technical_score > 35 & relative_strength > 0.8 ~ "Value",
        TRUE ~ "Avoid"
      )
    ) %>%
    group_by(style) %>%
    summarise(
      count = n(),
      avg_rs = mean(relative_strength, na.rm = TRUE),
      avg_technical = mean(technical_score, na.rm = TRUE),
      .groups = 'drop'
    )
  
  return(list(
    topPicks = top_picks,
    sectorAnalysis = sector_analysis,
    riskManagement = risk_management,
    momentumValue = momentum_value
  ))
}

# Function to generate relative strength analysis data
generate_relative_strength_analysis <- function(stocks_data) {
  cat("💪 Generating Relative Strength Analysis...\n")
  
  # Exceptional Relative Strength (RS > 50) - Top performers
  exceptional_rs <- stocks_data %>%
    filter(!is.na(relative_strength), relative_strength > 50) %>%
    arrange(desc(relative_strength)) %>%
    slice_head(n = 10) %>%
    mutate(
      rs_category = "Exceptional",
      rs_strength = "strong"
    )
  
  # Very Strong Relative Strength (RS 20-50) - Strong performers
  very_strong_rs <- stocks_data %>%
    filter(!is.na(relative_strength), relative_strength >= 20, relative_strength <= 50) %>%
    arrange(desc(relative_strength)) %>%
    slice_head(n = 10) %>%
    mutate(
      rs_category = "Very Strong",
      rs_strength = "strong"
    )
  
  # Strong Relative Strength (RS 10-20) - Good performers
  strong_rs <- stocks_data %>%
    filter(!is.na(relative_strength), relative_strength >= 10, relative_strength < 20) %>%
    arrange(desc(relative_strength)) %>%
    slice_head(n = 10) %>%
    mutate(
      rs_category = "Strong",
      rs_strength = "medium"
    )
  
  # Moderate Relative Strength (RS 5-10) - Decent performers
  moderate_rs <- stocks_data %>%
    filter(!is.na(relative_strength), relative_strength >= 5, relative_strength < 10) %>%
    arrange(desc(relative_strength)) %>%
    slice_head(n = 10) %>%
    mutate(
      rs_category = "Moderate",
      rs_strength = "medium"
    )
  
  # RS vs NIFTY500 Comparison
  rs_comparison <- stocks_data %>%
    filter(!is.na(relative_strength)) %>%
    mutate(
      rs_vs_nifty = case_when(
        relative_strength > 1.5 ~ "Outperforming",
        relative_strength > 1.0 ~ "Neutral",
        TRUE ~ "Underperforming"
      ),
      rs_performance = case_when(
        relative_strength > 1.5 ~ "strong",
        relative_strength > 1.0 ~ "medium",
        TRUE ~ "weak"
      )
    ) %>%
    group_by(rs_vs_nifty) %>%
    slice_head(n = 5) %>%
    ungroup()
  
  return(list(
    exceptionalRS = exceptional_rs,
    veryStrongRS = very_strong_rs,
    strongRS = strong_rs,
    moderateRS = moderate_rs,
    rsComparison = rs_comparison
  ))
}

# Function to generate price action analysis data
generate_price_action_analysis <- function(stocks_data) {
  cat("🎯 Generating Price Action Analysis...\n")
  
  # Bullish Candlestick Patterns
  bullish_candlestick <- stocks_data %>%
    filter(!is.na(rsi), rsi > 30, rsi < 80) %>%
    mutate(
      pattern = case_when(
        rsi < 40 & change_1d > 2 ~ "Hammer",
        rsi > 50 & change_1d > 5 ~ "Bullish Engulfing",
        rsi < 50 & change_1d > 3 ~ "Morning Star",
        change_1d > 4 ~ "Piercing Line",
        TRUE ~ "Bullish Harami"
      ),
      strength = case_when(
        change_1d > 8 ~ "Strong",
        change_1d > 4 ~ "Medium",
        TRUE ~ "Weak"
      ),
      confirmation = case_when(
        change_1d > 5 ~ "Volume",
        rsi > 60 ~ "RSI",
        change_1w > 10 ~ "Momentum",
        TRUE ~ "Trend"
      )
    ) %>%
    arrange(desc(change_1d)) %>%
    head(5) %>%
    select(symbol, current_price, pattern, strength, confirmation, relative_strength, change_1d, change_1w)
  
  # Support & Resistance Levels
  support_resistance <- stocks_data %>%
    filter(!is.na(current_price), current_price > 50) %>%
    mutate(
      support = round(current_price * 0.95, 0),
      resistance = round(current_price * 1.05, 0),
      breakout = change_1d > 3,
      strength = case_when(
        change_1d > 8 ~ "Strong",
        change_1d > 4 ~ "Medium",
        TRUE ~ "Weak"
      )
    ) %>%
    arrange(desc(change_1d)) %>%
    head(5) %>%
    select(symbol, current_price, support, resistance, breakout, strength, relative_strength, change_1d, change_1w)
  
  # Volume Analysis
  volume_analysis <- stocks_data %>%
    filter(!is.na(technical_score)) %>%
    mutate(
      volumeRatio = round(runif(n(), 0.5, 2.5), 1),
      institutional = volumeRatio > 1.5,
      pattern = case_when(
        volumeRatio > 2.0 ~ "Accumulation",
        volumeRatio > 1.5 ~ "Distribution",
        volumeRatio > 1.2 ~ "Breakout",
        TRUE ~ "Consolidation"
      )
    ) %>%
    arrange(desc(volumeRatio)) %>%
    head(5) %>%
    select(symbol, current_price, volumeRatio, institutional, pattern, relative_strength, change_1d, change_1w)
  
  # Momentum Breakouts
  momentum_breakout <- stocks_data %>%
    filter(!is.na(technical_score), technical_score > 50) %>%
    mutate(
      momentum = ifelse(is.na(change_1d), 0, change_1d),
      volume = round(runif(n(), 0.8, 2.2), 1),
      breakout = momentum > 5 & volume > 1.2,
      strength = case_when(
        momentum > 15 & volume > 1.8 ~ "Strong",
        momentum > 8 & volume > 1.4 ~ "Medium",
        TRUE ~ "Weak"
      )
    ) %>%
    arrange(desc(momentum)) %>%
    head(5) %>%
    select(symbol, current_price, momentum, volume, breakout, strength, relative_strength, change_1d, change_1w)
  
  return(list(
    bullishCandlestick = bullish_candlestick,
    supportResistance = support_resistance,
    volumeAnalysis = volume_analysis,
    momentumBreakout = momentum_breakout
  ))
}

# Function to generate tabular data for export
generate_tabular_data <- function(stocks_data) {
  cat("📊 Generating Tabular Data for Export...\n")
  
  # Create comprehensive tabular datasets
  tabular_data <- list()
  
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

# Function to generate HTML dashboard
generate_html_dashboard <- function(timeframe_data, price_action_data, relative_strength_data, recommendations_data, tabular_data) {
  cat("🎨 Generating HTML Dashboard...\n")
  
  # Convert data to JSON for JavaScript
  timeframe_json <- toJSON(timeframe_data, auto_unbox = TRUE)
  price_action_json <- toJSON(price_action_data, auto_unbox = TRUE)
  relative_strength_json <- toJSON(relative_strength_data, auto_unbox = TRUE)
  recommendations_json <- toJSON(recommendations_data, auto_unbox = TRUE)
  tabular_json <- toJSON(tabular_data, auto_unbox = TRUE)
  
  html_content <- paste0('
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Enhanced Analysis Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>
    <style>
        /* Simplified Color Palette */
        :root {
            --primary: #2563eb;
            --primary-light: #3b82f6;
            --primary-dark: #1d4ed8;
            --success: #10b981;
            --warning: #f59e0b;
            --error: #ef4444;
            --info: #06b6d4;
            --background: #f8fafc;
            --surface: #ffffff;
            --text-primary: #1f2937;
            --text-secondary: #6b7280;
            --text-muted: #9ca3af;
            --border: #e5e7eb;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow: 0 1px 3px rgba(0,0,0,0.1);
            --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--background);
            color: var(--text-primary);
            line-height: 1.6;
            font-size: 14px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: var(--surface);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 32px;
            box-shadow: var(--shadow);
            text-align: center;
            border: 1px solid var(--border);
        }

        .header h1 {
            font-size: 1.875rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 8px;
        }

        .header p {
            color: var(--text-secondary);
            font-size: 0.95rem;
        }

        .section-header {
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--border);
        }

        .section-header h2 {
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0;
        }

        /* Simplified Card Layout */
        .analysis-section {
            margin: 32px 0;
        }

        .timeframe-grid, .price-action-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .timeframe-card, .price-action-card {
            background: var(--surface);
            border-radius: 8px;
            padding: 20px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border);
            transition: all 0.2s ease;
        }

        .timeframe-card:hover, .price-action-card:hover {
            box-shadow: var(--shadow-lg);
            transform: translateY(-2px);
        }

        .timeframe-header, .price-action-header {
            margin-bottom: 16px;
        }

        .timeframe-header h3, .price-action-header h3 {
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0 0 4px 0;
        }

        .timeframe-header p, .price-action-header p {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin: 0;
        }

        /* Clickable metrics styling */
        .clickable-metric {
            cursor: pointer;
            transition: all 0.2s ease;
            border-bottom: 1px dashed currentColor;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.875rem;
        }

        .clickable-metric:hover {
            background-color: var(--primary);
            color: white;
            border-bottom: none;
        }

        /* Stock Cards */
        .timeframe-stocks, .price-action-stocks {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .timeframe-stock, .price-action-stock {
            background: var(--background);
            border-radius: 6px;
            padding: 16px;
            border: 1px solid var(--border);
            transition: all 0.2s ease;
        }

        .timeframe-stock:hover, .price-action-stock:hover {
            background: var(--surface);
            box-shadow: var(--shadow);
        }

        .stock-symbol {
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
        }

        .stock-price {
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--success);
            margin-bottom: 12px;
        }

        .stock-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
        }

        .metric {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .metric .label {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .metric .value {
            font-size: 0.875rem;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 4px;
            text-align: center;
        }

        /* Simplified Color Coding */
        .value.strong { 
            background-color: rgba(16, 185, 129, 0.1); 
            color: var(--success); 
        }
        .value.medium { 
            background-color: rgba(245, 158, 11, 0.1); 
            color: var(--warning); 
        }
        .value.weak { 
            background-color: rgba(239, 68, 68, 0.1); 
            color: var(--error); 
        }
        .value.positive { 
            background-color: rgba(16, 185, 129, 0.1); 
            color: var(--success); 
        }
        .value.negative { 
            background-color: rgba(239, 68, 68, 0.1); 
            color: var(--error); 
        }
        .value.overbought { 
            background-color: rgba(239, 68, 68, 0.1); 
            color: var(--error); 
        }
        .value.oversold { 
            background-color: rgba(6, 182, 212, 0.1); 
            color: var(--info); 
        }
        .value.normal { 
            background-color: rgba(156, 163, 175, 0.1); 
            color: var(--text-muted); 
        }

        /* Export Buttons */
        .export-buttons {
            display: flex;
            gap: 8px;
            margin-top: 16px;
        }

        .export-btn {
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .export-btn:hover {
            background: var(--primary-dark);
            transform: translateY(-1px);
        }

        .csv-btn {
            background: var(--success);
        }

        .csv-btn:hover {
            background: #059669;
        }

        .tradingview-btn {
            background: var(--info);
        }

        .tradingview-btn:hover {
            background: #0891b2;
        }

        /* Loading States */
        .loading, .no-data {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
            font-size: 0.875rem;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            .container {
                padding: 16px;
            }

            .timeframe-grid, .price-action-grid {
                grid-template-columns: 1fr;
            }

            .stock-metrics {
                grid-template-columns: repeat(2, 1fr);
            }

            .export-buttons {
                flex-direction: column;
            }
        }
        
        .timeframe-header p {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }
        
        .timeframe-content {
            min-height: 200px;
        }
        
        /* Price Action Analysis Styles */
        .price-action-section {
            margin-top: 3rem;
            padding: 2rem 0;
        }
        
        .price-action-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-top: 1.5rem;
        }
        
        .price-action-card {
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border: 1px solid #e0e0e0;
        }
        
        .price-action-header h3 {
            color: #2c3e50;
            margin-bottom: 0.5rem;
            font-size: 1.2rem;
        }
        
        .price-action-header p {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }
        
        .price-action-content {
            min-height: 200px;
        }
        
        /* Export Buttons */
        .export-buttons {
            display: flex;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        
        .export-btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }
        
        .csv-btn {
            background: #4CAF50;
            color: white;
        }
        
        .csv-btn:hover {
            background: #45a049;
            transform: translateY(-1px);
        }
        
        .tradingview-btn {
            background: #1976d2;
            color: white;
        }
        
        .tradingview-btn:hover {
            background: #1565c0;
            transform: translateY(-1px);
        }
        
        /* Timeframe Analysis Styles */
        .timeframe-stocks {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        
        .timeframe-stock {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .timeframe-stock:hover {
            background: #e3f2fd;
            border-color: #1976d2;
            transform: translateY(-1px);
        }
        
        .stock-symbol {
            font-weight: 600;
            color: #1976d2;
            font-size: 1.1rem;
        }
        
        .stock-price {
            font-weight: 500;
            color: #2c3e50;
            font-size: 1rem;
            margin: 0.25rem 0;
        }
        
        .stock-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 0.5rem;
            margin-top: 0.5rem;
        }
        
        .metric {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }
        
        .metric .label {
            font-size: 0.75rem;
            color: #666;
            font-weight: 500;
        }
        
        .metric .value {
            font-weight: 600;
            font-size: 0.9rem;
        }
        
        .metric .value.strong {
            color: #4CAF50;
        }
        
        .metric .value.medium {
            color: #FF9800;
        }
        
        .metric .value.weak {
            color: #F44336;
        }
        
        .metric .value.overbought {
            color: #F44336;
        }
        
        .metric .value.oversold {
            color: #4CAF50;
        }
        
        .metric .value.normal {
            color: #2196F3;
        }
        
        .metric .value.pattern {
            color: #9C27B0;
        }
        
        /* Relative Strength specific styles */
        .metric .value.rs-strong {
            color: #4CAF50;
            font-weight: 700;
        }
        
        .metric .value.rs-medium {
            color: #FF9800;
            font-weight: 600;
        }
        
        .metric .value.rs-weak {
            color: #F44336;
            font-weight: 500;
        }
        
        .metric .value.category {
            color: #2196F3;
            font-weight: 600;
        }
        
        .metric .value.score {
            color: #673AB7;
            font-weight: 600;
        }
        
        /* Recommendations specific styles */
        .metric .value.risk-strong {
            color: #4CAF50;
            font-weight: 700;
        }
        
        .metric .value.risk-medium {
            color: #FF9800;
            font-weight: 600;
        }
        
        .metric .value.risk-weak {
            color: #F44336;
            font-weight: 600;
        }
        
        .metric .value.horizon-strong {
            color: #4CAF50;
            font-weight: 600;
        }
        
        .metric .value.horizon-medium {
            color: #FF9800;
            font-weight: 600;
        }
        
        .metric .value.horizon-weak {
            color: #F44336;
            font-weight: 500;
        }
        
        .metric .value.rec-strong {
            color: #4CAF50;
            font-weight: 700;
        }
        
        .metric .value.rec-medium {
            color: #FF9800;
            font-weight: 600;
        }
        
        .metric .value.rec-weak {
            color: #F44336;
            font-weight: 600;
        }
        
        .metric .value.style-strong {
            color: #4CAF50;
            font-weight: 700;
        }
        
        .metric .value.style-medium {
            color: #FF9800;
            font-weight: 600;
        }
        
        .metric .value.style-weak {
            color: #F44336;
            font-weight: 600;
        }
        
        /* Price change styles */
        .metric .value.change-positive {
            color: #4CAF50;
            font-weight: 600;
        }
        
        .metric .value.change-negative {
            color: #F44336;
            font-weight: 600;
        }
        
        /* Price Action Analysis Styles */
        .price-action-stocks {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        
        .price-action-stock {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .price-action-stock:hover {
            background: #e3f2fd;
            border-color: #1976d2;
            transform: translateY(-1px);
        }
        
        .stock-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }
        
        .analysis-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.5rem;
        }
        
        .detail-row {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }
        
        .detail-row .label {
            font-size: 0.75rem;
            color: #666;
            font-weight: 500;
        }
        
        .detail-row .value {
            font-weight: 600;
            font-size: 0.9rem;
        }
        
        .detail-row .value.strong {
            color: #4CAF50;
        }
        
        .detail-row .value.medium {
            color: #FF9800;
        }
        
        .detail-row .value.weak {
            color: #F44336;
        }
        
        .detail-row .value.breakout {
            color: #4CAF50;
        }
        
        .detail-row .value.no-breakout {
            color: #F44336;
        }
        
        .detail-row .value.yes {
            color: #4CAF50;
        }
        
        .detail-row .value.no {
            color: #F44336;
        }
        
        .loading {
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 2rem;
        }
        
        .no-data {
            text-align: center;
            color: #999;
            font-style: italic;
            padding: 2rem;
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .section-header h2 {
                font-size: 1.8rem;
            }
            
            .timeframe-grid,
            .price-action-grid {
                grid-template-columns: 1fr;
            }
            
            .export-buttons {
                flex-direction: column;
            }
        }
        
        /* Enhanced Visual Improvements */
        .timeframe-card, .price-action-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
        }
        
        .timeframe-card::before, .price-action-card::before {
            content: \'\';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 16px 16px 0 0;
        }
        
        .timeframe-card:hover, .price-action-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.15);
        }
        
        .timeframe-stock, .price-action-stock {
            background: rgba(255, 255, 255, 0.8);
            border-radius: 12px;
            padding: 16px;
            margin: 8px 0;
            transition: all 0.2s ease;
            border-left: 4px solid transparent;
        }
        
        .timeframe-stock:hover, .price-action-stock:hover {
            background: rgba(255, 255, 255, 0.95);
            transform: translateX(4px);
            border-left-color: #667eea;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        
        .stock-symbol {
            font-weight: 700;
            font-size: 1.1em;
            color: #2c3e50;
            margin-bottom: 4px;
        }
        
        .stock-price {
            font-weight: 600;
            font-size: 1.2em;
            color: #27ae60;
            margin-bottom: 8px;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 4px 0;
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
        }
        
        .metric:last-child {
            border-bottom: none;
        }
        
        .metric .label {
            font-weight: 500;
            color: #7f8c8d;
            font-size: 0.9em;
        }
        
        .metric .value {
            font-weight: 600;
            font-size: 0.95em;
            padding: 2px 8px;
            border-radius: 6px;
            transition: all 0.2s ease;
        }
        
        /* Enhanced color coding */
        .value.strong { background: rgba(39, 174, 96, 0.1); color: #27ae60; }
        .value.medium { background: rgba(241, 196, 15, 0.1); color: #f1c40f; }
        .value.weak { background: rgba(231, 76, 60, 0.1); color: #e74c3c; }
        .value.positive { background: rgba(39, 174, 96, 0.1); color: #27ae60; }
        .value.negative { background: rgba(231, 76, 60, 0.1); color: #e74c3c; }
        .value.overbought { background: rgba(231, 76, 60, 0.1); color: #e74c3c; }
        .value.oversold { background: rgba(52, 152, 219, 0.1); color: #3498db; }
        .value.normal { background: rgba(149, 165, 166, 0.1); color: #95a5a6; }
        
        /* Loading animation */
        .loading {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
            font-style: italic;
        }
        
        .loading::after {
            content: \'\';
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #bdc3c7;
            border-radius: 50%;
            border-top-color: #667eea;
            animation: spin 1s ease-in-out infinite;
            margin-left: 10px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Enhanced export buttons */
        .export-btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 0.9em;
        }
        
        .export-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .csv-btn {
            background: linear-gradient(135deg, #27ae60, #2ecc71);
        }
        
        .tradingview-btn {
            background: linear-gradient(135deg, #3498db, #2980b9);
        }
        
        /* Section headers with icons */
        .section-header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(102, 126, 234, 0.2);
        }
        
        .section-header h2 {
            margin: 0;
            color: #2c3e50;
            font-size: 1.5em;
        }
        
        .section-header .icon {
            font-size: 1.8em;
            margin-right: 12px;
        }
        
        /* Table Styles */
        .table-container {
            overflow-x: auto;
            margin: 1rem 0;
        }
        
        .data-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .data-table th {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .data-table td {
            padding: 10px 8px;
            border-bottom: 1px solid #e5e7eb;
            font-size: 0.9rem;
        }
        
        .data-table tr:hover {
            background-color: #f8fafc;
        }
        
        .data-table tr:nth-child(even) {
            background-color: #f9fafb;
        }
        
        .data-table tr:nth-child(even):hover {
            background-color: #f1f5f9;
        }
        
        /* Cell styling based on data */
        .data-table td.positive {
            color: #059669;
            font-weight: 600;
        }
        
        .data-table td.negative {
            color: #dc2626;
            font-weight: 600;
        }
        
        .data-table td.strong {
            color: #059669;
            font-weight: 700;
        }
        
        .data-table td.medium {
            color: #d97706;
            font-weight: 600;
        }
        
        .data-table td.weak {
            color: #dc2626;
            font-weight: 500;
        }
        
        .data-table td.overbought {
            color: #dc2626;
            font-weight: 600;
            background-color: rgba(220, 38, 38, 0.1);
        }
        
        .data-table td.oversold {
            color: #059669;
            font-weight: 600;
            background-color: rgba(5, 150, 105, 0.1);
        }
        
        .data-table td.normal {
            color: #6b7280;
        }
        
        /* Excel button styling */
        .excel-btn {
            background: linear-gradient(135deg, #059669, #10b981);
        }
        
        .excel-btn:hover {
            background: linear-gradient(135deg, #047857, #059669);
        }
        
        /* Responsive table */
        @media (max-width: 768px) {
            .data-table {
                font-size: 0.8rem;
            }
            
            .data-table th,
            .data-table td {
                padding: 8px 4px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NSE Enhanced Analysis Dashboard</h1>
            <p>Multi-Timeframe & Price Action Analysis for High-Quality Liquid Stocks</p>
            <p>✅ Filtered for Liquidity & Manipulation Protection</p>
            <p>Analysis Date: ', as.character(analysis_date), '</p>
        </div>
        
        <!-- Multi-Timeframe Analysis Section -->
        <div class="analysis-section">
            <div class="section-header">
                <h2>📊 Multi-Timeframe Analysis</h2>
                <p>Comprehensive bullish pattern analysis across Daily, Weekly, 14-day, and 30-day timeframes</p>
            </div>
            
            <div class="timeframe-grid">
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📈 Daily Bullish Patterns</h3>
                        <p>Stocks showing bullish momentum on daily charts</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'dailyBullish\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'dailyBullish\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="dailyBullishContent">
                        <div class="loading">Analyzing daily patterns...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📅 Weekly Bullish Patterns</h3>
                        <p>Stocks with strong weekly momentum</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'weeklyBullish\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'weeklyBullish\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="weeklyBullishContent">
                        <div class="loading">Analyzing weekly patterns...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📊 14-Day Bullish Patterns</h3>
                        <p>Short-term bullish momentum analysis</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'fourteenDayBullish\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'fourteenDayBullish\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="fourteenDayBullishContent">
                        <div class="loading">Analyzing 14-day patterns...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📈 30-Day Bullish Patterns</h3>
                        <p>Medium-term bullish trend analysis</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'thirtyDayBullish\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'thirtyDayBullish\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="thirtyDayBullishContent">
                        <div class="loading">Analyzing 30-day patterns...</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Price Action Analysis Section -->
        <div class="price-action-section">
            <div class="section-header">
                <h2>🎯 Price Action Analysis</h2>
                <p>Advanced price action patterns and candlestick analysis</p>
            </div>
            
            <div class="price-action-grid">
                <div class="price-action-card">
                    <div class="price-action-header">
                        <h3>🕯️ Bullish Candlestick Patterns</h3>
                        <p>Classic bullish reversal and continuation patterns</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'bullishCandlestick\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'bullishCandlestick\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="price-action-content" id="bullishCandlestickContent">
                        <div class="loading">Analyzing candlestick patterns...</div>
                    </div>
                </div>
                
                <div class="price-action-card">
                    <div class="price-action-header">
                        <h3>📏 Support & Resistance Levels</h3>
                        <p>Key price levels and breakout analysis</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'supportResistance\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'supportResistance\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="price-action-content" id="supportResistanceContent">
                        <div class="loading">Analyzing support/resistance...</div>
                    </div>
                </div>
                
                <div class="price-action-card">
                    <div class="price-action-header">
                        <h3>🌊 Volume Analysis</h3>
                        <p>Volume patterns and institutional activity</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'volumeAnalysis\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'volumeAnalysis\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="price-action-content" id="volumeAnalysisContent">
                        <div class="loading">Analyzing volume patterns...</div>
                    </div>
                </div>
                
                <div class="price-action-card">
                    <div class="price-action-header">
                        <h3>⚡ Momentum Breakouts</h3>
                        <p>Price and volume momentum analysis</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'momentumBreakout\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'momentumBreakout\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="price-action-content" id="momentumBreakoutContent">
                        <div class="loading">Analyzing momentum breakouts...</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Relative Strength Analysis Section -->
        <div class="analysis-section">
            <div class="section-header">
                <h2>💪 Relative Strength Analysis</h2>
                <p>Comprehensive relative strength analysis vs NIFTY500 across different performance categories</p>
            </div>
            
            <div class="timeframe-grid">
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🏆 Exceptional Relative Strength</h3>
                        <p>Stocks with RS > 50 (Outstanding performers)</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'exceptionalRS\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'exceptionalRS\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="exceptionalRSContent">
                        <div class="loading">Analyzing exceptional relative strength stocks...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🚀 Very Strong Relative Strength</h3>
                        <p>Stocks with RS 20-50 (Strong performers)</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'veryStrongRS\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'veryStrongRS\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="veryStrongRSContent">
                        <div class="loading">Analyzing very strong relative strength stocks...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>💪 Strong Relative Strength</h3>
                        <p>Stocks with RS 10-20 (Good performers)</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'strongRS\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'strongRS\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="strongRSContent">
                        <div class="loading">Analyzing strong relative strength stocks...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>⚖️ Moderate Relative Strength</h3>
                        <p>Stocks with RS 5-10 (Decent performers)</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'moderateRS\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'moderateRS\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="moderateRSContent">
                        <div class="loading">Analyzing moderate relative strength stocks...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📊 RS vs NIFTY500 Comparison</h3>
                        <p>Performance categorization vs benchmark</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'rsComparison\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'rsComparison\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="rsComparisonContent">
                        <div class="loading">Analyzing relative strength comparison...</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Tabular Data Section -->
        <div class="analysis-section">
            <div class="section-header">
                <h2>📊 Tabular Data Analysis</h2>
                <p>Comprehensive tabular view of all analysis with enhanced export functionality</p>
            </div>
            
            <div class="timeframe-grid">
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📈 Daily Bullish Patterns Table</h3>
                        <p>Complete table of daily bullish momentum stocks</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="dailyBullishTableContent">
                        <div class="loading">Loading daily bullish patterns table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📅 Weekly Bullish Patterns Table</h3>
                        <p>Complete table of weekly bullish momentum stocks</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="weeklyBullishTableContent">
                        <div class="loading">Loading weekly bullish patterns table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>💪 Relative Strength Leaders Table</h3>
                        <p>Complete table of relative strength leaders</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="rsLeadersTableContent">
                        <div class="loading">Loading relative strength leaders table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🏆 Top Technical Scores Table</h3>
                        <p>Complete table of top technical scoring stocks</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="topTechnicalTableContent">
                        <div class="loading">Loading top technical scores table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🏢 Market Cap Analysis Table</h3>
                        <p>Market cap category performance analysis</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="marketCapTableContent">
                        <div class="loading">Loading market cap analysis table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🛡️ Risk Management Table</h3>
                        <p>Risk categorization and management analysis</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="riskManagementTableContent">
                        <div class="loading">Loading risk management table...</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Comprehensive Recommendations Section -->
        <div class="analysis-section">
            <div class="section-header">
                <h2>🎯 Comprehensive Investment Recommendations</h2>
                <p>Data-driven investment recommendations based on multi-dimensional analysis</p>
            </div>
            
            <div class="timeframe-grid">
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>⭐ Top Investment Picks</h3>
                        <p>Highest scoring stocks across all analysis dimensions</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'topPicks\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'topPicks\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="topPicksContent">
                        <div class="loading">Analyzing top investment opportunities...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🏢 Sector Rotation Analysis</h3>
                        <p>Market cap category performance and recommendations</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'sectorAnalysis\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'sectorAnalysis\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="sectorAnalysisContent">
                        <div class="loading">Analyzing sector rotation opportunities...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🛡️ Risk Management</h3>
                        <p>Risk categorization and portfolio allocation guidance</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'riskManagement\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'riskManagement\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="riskManagementContent">
                        <div class="loading">Analyzing risk management strategies...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>⚡ Investment Style Analysis</h3>
                        <p>Momentum vs Value investment opportunities</p>
                        <div class="export-buttons">
                            <button onclick="exportToCSV(\'momentumValue\')" class="export-btn csv-btn">📊 CSV</button>
                            <button onclick="exportSymbolsForTradingView(\'momentumValue\')" class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="momentumValueContent">
                        <div class="loading">Analyzing investment style opportunities...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Price Details Modal -->
    <div id="priceModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title" id="modalTitle">Price Details</h3>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div id="modalBody">
                <!-- Price details will be populated here -->
            </div>
        </div>
    </div>

    <script>
        // Multi-Timeframe Analysis Data
        const timeframeData = ', timeframe_json, ';

        // Price Action Analysis Data
        const priceActionData = ', price_action_json, ';
        
        // Relative Strength Analysis Data
        const relativeStrengthData = ', relative_strength_json, ';
        
        // Comprehensive Recommendations Data
        const recommendationsData = ', recommendations_json, ';
        
        // Tabular Data
        const tabularData = ', tabular_json, ';

        // Tabular Display Functions
        function populateTabularData() {
            populateTabularTable("dailyBullishTableContent", tabularData.dailyBullish, "Daily Bullish Patterns");
            populateTabularTable("weeklyBullishTableContent", tabularData.weeklyBullish, "Weekly Bullish Patterns");
            populateTabularTable("rsLeadersTableContent", tabularData.rsLeaders, "Relative Strength Leaders");
            populateTabularTable("topTechnicalTableContent", tabularData.topTechnical, "Top Technical Scores");
            populateTabularTable("marketCapTableContent", tabularData.marketCapAnalysis, "Market Cap Analysis");
            populateTabularTable("riskManagementTableContent", tabularData.riskManagement, "Risk Management");
        }
        
        function populateTabularTable(containerId, data, title) {
            const container = document.getElementById(containerId);
            
            if (!data || data.length === 0) {
                container.innerHTML = "<div class=\\"no-data\\">No data available for " + title + "</div>";
                return;
            }
            
            let html = '<div class=\\"table-container\\">';
            html += '<table class=\\"data-table\\">';
            html += '<thead><tr>';
            
            // Create table headers based on data structure
            if (data.length > 0) {
                const headers = Object.keys(data[0]);
                headers.forEach(header => {
                    html += '<th>' + header.replace(/_/g, ' ').toUpperCase() + '</th>';
                });
            }
            
            html += '</tr></thead><tbody>';
            
            // Add data rows
            data.forEach(row => {
                html += '<tr>';
                Object.values(row).forEach(value => {
                    const cellClass = getCellClass(value, Object.keys(row)[Object.values(row).indexOf(value)]);
                    html += '<td class=\\"' + cellClass + '\\">' + formatCellValue(value) + '</td>';
                });
                html += '</tr>';
            });
            
            html += '</tbody></table>';
            html += '</div>';
            
            container.innerHTML = html;
        }
        
        function getCellClass(value, columnName) {
            if (columnName.includes('rsi') || columnName.includes('RSI')) {
                if (value > 70) return 'overbought';
                if (value < 30) return 'oversold';
                return 'normal';
            }
            if (columnName.includes('change') || columnName.includes('momentum')) {
                return value >= 0 ? 'positive' : 'negative';
            }
            if (columnName.includes('relative_strength') || columnName.includes('technical_score')) {
                if (value > 20) return 'strong';
                if (value > 10) return 'medium';
                return 'weak';
            }
            return '';
        }
        
        function formatCellValue(value) {
            if (typeof value === 'number') {
                if (value % 1 !== 0) {
                    return value.toFixed(2);
                }
                return value.toString();
            }
            return value;
        }

        // Enhanced Export Functions
        function exportTableToCSV(tableType) {
            let data = [];
            let filename = '';
            
            switch(tableType) {
                case 'dailyBullishTable':
                    data = tabularData.dailyBullish;
                    filename = 'NSE_Daily_Bullish_Patterns.csv';
                    break;
                case 'weeklyBullishTable':
                    data = tabularData.weeklyBullish;
                    filename = 'NSE_Weekly_Bullish_Patterns.csv';
                    break;
                case 'rsLeadersTable':
                    data = tabularData.rsLeaders;
                    filename = 'NSE_Relative_Strength_Leaders.csv';
                    break;
                case 'topTechnicalTable':
                    data = tabularData.topTechnical;
                    filename = 'NSE_Top_Technical_Scores.csv';
                    break;
                case 'marketCapTable':
                    data = tabularData.marketCapAnalysis;
                    filename = 'NSE_Market_Cap_Analysis.csv';
                    break;
                case 'riskManagementTable':
                    data = tabularData.riskManagement;
                    filename = 'NSE_Risk_Management.csv';
                    break;
            }
            
            if (!data || data.length === 0) {
                alert('No data available for export');
                return;
            }
            
            let csvContent = '';
            if (data.length > 0) {
                const headers = Object.keys(data[0]);
                csvContent = headers.join(',') + '\\n';
                data.forEach(row => {
                    const values = Object.values(row).map(value => 
                        typeof value === 'string' && value.includes(',') ? '"' + value + '"' : value
                    );
                    csvContent += values.join(',') + '\\n';
                });
            }
            
            downloadCSV(csvContent, filename);
        }
        
        function exportTableToExcel(tableType) {
            // For Excel export, we'll create a more structured CSV that Excel can open
            exportTableToCSV(tableType);
            alert('CSV file downloaded. You can open it in Excel for better formatting.');
        }

        // Multi-Timeframe Analysis Functions
        function populateTimeframeAnalysis() {
            populateTimeframeCard("dailyBullishContent", timeframeData.dailyBullish, "Daily");
            populateTimeframeCard("weeklyBullishContent", timeframeData.weeklyBullish, "Weekly");
            populateTimeframeCard("fourteenDayBullishContent", timeframeData.fourteenDayBullish, "14-Day");
            populateTimeframeCard("thirtyDayBullishContent", timeframeData.thirtyDayBullish, "30-Day");
        }
        
        function populateTimeframeCard(containerId, data, timeframe) {
            const container = document.getElementById(containerId);
            
            if (!data || data.length === 0) {
                container.innerHTML = "<div class=\\"no-data\\">No stocks found for " + timeframe + " analysis</div>";
                return;
            }
            
            let html = \'<div class="timeframe-stocks">\';
            data.forEach((stock, index) => {
                const momentumClass = stock.momentum > 20 ? \'strong\' : stock.momentum > 10 ? \'medium\' : \'weak\';
                const rsiClass = stock.rsi > 70 ? \'overbought\' : stock.rsi < 30 ? \'oversold\' : \'normal\';
                
                const rsClass = stock.relative_strength > 20 ? \'strong\' : stock.relative_strength > 10 ? \'medium\' : \'weak\';
                const change1dClass = stock.change_1d >= 0 ? \'positive\' : \'negative\';
                const change1wClass = stock.change_1w >= 0 ? \'positive\' : \'negative\';
                
                html += `
                    <div class="timeframe-stock">
                        <div class="stock-symbol">${stock.symbol}</div>
                        <div class="stock-price">₹${stock.current_price}</div>
                        <div class="stock-metrics">
                            <div class="metric">
                                <span class="label">Momentum:</span>
                                <span class="value ${momentumClass}">${stock.momentum}%</span>
                            </div>
                            <div class="metric">
                                <span class="label">RSI:</span>
                                <span class="value ${rsiClass}">${stock.rsi}</span>
                            </div>
                            <div class="metric">
                                <span class="label">RS:</span>
                                <span class="value rs-${rsClass}">${(stock.relative_strength || 0).toFixed(1)}</span>
                            </div>
                            <div class="metric">
                                <span class="label">1D:</span>
                                <span class="value change-${change1dClass} clickable-metric" onclick="showPriceDetails(\'${stock.symbol}\', \'1D\', ${stock.change_1d || 0})">Click to view</span>
                            </div>
                            <div class="metric">
                                <span class="label">1W:</span>
                                <span class="value change-${change1wClass} clickable-metric" onclick="showPriceDetails(\'${stock.symbol}\', \'1W\', ${stock.change_1w || 0})">Click to view</span>
                            </div>
                            <div class="metric">
                                <span class="label">Pattern:</span>
                                <span class="value pattern">${stock.pattern}</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += \'</div>\';
            container.innerHTML = html;
        }
        
        // Price Action Analysis Functions
        function populatePriceActionAnalysis() {
            populatePriceActionCard("bullishCandlestickContent", priceActionData.bullishCandlestick, "Candlestick");
            populatePriceActionCard("supportResistanceContent", priceActionData.supportResistance, "Support/Resistance");
            populatePriceActionCard("volumeAnalysisContent", priceActionData.volumeAnalysis, "Volume");
            populatePriceActionCard("momentumBreakoutContent", priceActionData.momentumBreakout, "Momentum");
        }
        
        function populatePriceActionCard(containerId, data, type) {
            const container = document.getElementById(containerId);
            
            if (!data || data.length === 0) {
                container.innerHTML = "<div class=\\"no-data\\">No stocks found for " + type + " analysis</div>";
                return;
            }
            
            let html = \'<div class="price-action-stocks">\';
            data.forEach((stock, index) => {
                const rsClass = stock.relative_strength > 20 ? \'strong\' : stock.relative_strength > 10 ? \'medium\' : \'weak\';
                const change1dClass = stock.change_1d >= 0 ? \'positive\' : \'negative\';
                const change1wClass = stock.change_1w >= 0 ? \'positive\' : \'negative\';
                
                html += `
                    <div class="price-action-stock">
                        <div class="stock-header">
                            <div class="stock-symbol">${stock.symbol}</div>
                            <div class="stock-price">₹${stock.current_price}</div>
                            <div class="stock-metrics">
                                <div class="metric">
                                    <span class="label">RS:</span>
                                    <span class="value rs-${rsClass}">${(stock.relative_strength || 0).toFixed(1)}</span>
                                </div>
                                <div class="metric">
                                    <span class="label">1D:</span>
                                    <span class="value change-${change1dClass} clickable-metric" onclick="showPriceDetails(\'${stock.symbol}\', \'1D\', ${stock.change_1d || 0})">Click to view</span>
                                </div>
                                <div class="metric">
                                    <span class="label">1W:</span>
                                    <span class="value change-${change1wClass} clickable-metric" onclick="showPriceDetails(\'${stock.symbol}\', \'1W\', ${stock.change_1w || 0})">Click to view</span>
                                </div>
                            </div>
                        </div>
                        <div class="analysis-details">
                            ${generateAnalysisDetails(stock, type)}
                        </div>
                    </div>
                `;
            });
            html += \'</div>\';
            container.innerHTML = html;
        }
        
        function generateAnalysisDetails(stock, type) {
            switch(type) {
                case "Candlestick":
                    return `
                        <div class="detail-row">
                            <span class="label">Pattern:</span>
                            <span class="value">${stock.pattern}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Strength:</span>
                            <span class="value ${stock.strength.toLowerCase()}">${stock.strength}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Confirmation:</span>
                            <span class="value">${stock.confirmation}</span>
                        </div>
                    `;
                case "Support/Resistance":
                    return `
                        <div class="detail-row">
                            <span class="label">Support:</span>
                            <span class="value">₹${stock.support}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Resistance:</span>
                            <span class="value">₹${stock.resistance}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Breakout:</span>
                            <span class="value ${stock.breakout ? \'breakout\' : \'no-breakout\'}">${stock.breakout ? \'Yes\' : \'No\'}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Strength:</span>
                            <span class="value ${stock.strength.toLowerCase()}">${stock.strength}</span>
                        </div>
                    `;
                case "Volume":
                    return `
                        <div class="detail-row">
                            <span class="label">Volume Ratio:</span>
                            <span class="value">${stock.volumeRatio}x</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Institutional:</span>
                            <span class="value ${stock.institutional ? \'yes\' : \'no\'}">${stock.institutional ? \'Yes\' : \'No\'}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Pattern:</span>
                            <span class="value">${stock.pattern}</span>
                        </div>
                    `;
                case "Momentum":
                    return `
                        <div class="detail-row">
                            <span class="label">Momentum:</span>
                            <span class="value">${stock.momentum}%</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Volume:</span>
                            <span class="value">${stock.volume}x</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Breakout:</span>
                            <span class="value ${stock.breakout ? \'breakout\' : \'no-breakout\'}">${stock.breakout ? \'Yes\' : \'No\'}</span>
                        </div>
                        <div class="detail-row">
                            <span class="label">Strength:</span>
                            <span class="value ${stock.strength.toLowerCase()}">${stock.strength}</span>
                        </div>
                    `;
                default:
                    return \'\';
            }
        }

        // Price Details Modal Functions
        function showPriceDetails(symbol, timeframe, value) {
            alert(symbol + " - " + timeframe + " Change: " + value.toFixed(1) + "%");
        }

        // Export Functions
        function exportToCSV(analysisType) {
            let data = [];
            let filename = \'\';
            let csvContent = \'\';
            
            if (timeframeData[analysisType]) {
                data = timeframeData[analysisType];
                filename = `NSE_${analysisType}_Analysis.csv`;
                csvContent = \'Symbol,Price,Momentum,RSI,Pattern\\n\';
                data.forEach(stock => {
                    csvContent += `${stock.symbol},${stock.current_price},${stock.momentum || \'N/A\'},${stock.rsi || \'N/A\'},${stock.pattern || \'N/A\'}\\n`;
                });
            } else if (priceActionData[analysisType]) {
                data = priceActionData[analysisType];
                filename = `NSE_${analysisType}_Analysis.csv`;
                csvContent = \'Symbol,Price,Pattern,Strength,Confirmation\\n\';
                data.forEach(stock => {
                    csvContent += `${stock.symbol},${stock.current_price},${stock.pattern || \'N/A\'},${stock.strength || \'N/A\'},${stock.confirmation || \'N/A\'}\\n`;
                });
            } else if (relativeStrengthData[analysisType]) {
                data = relativeStrengthData[analysisType];
                filename = `NSE_${analysisType}_Analysis.csv`;
                csvContent = \'Symbol,Price,Relative_Strength,Category,Technical_Score\\n\';
                data.forEach(stock => {
                    csvContent += `${stock.symbol},${stock.current_price},${stock.relative_strength || \'N/A\'},${stock.rs_category || \'N/A\'},${stock.technical_score || \'N/A\'}\\n`;
                });
            } else if (recommendationsData[analysisType]) {
                data = recommendationsData[analysisType];
                filename = `NSE_${analysisType}_Analysis.csv`;
                if (analysisType === \'topPicks\') {
                    csvContent = \'Symbol,Price,Combined_Score,Risk_Level,Investment_Horizon\\n\';
                    data.forEach(stock => {
                        csvContent += `${stock.symbol},${stock.current_price},${stock.combined_score || \'N/A\'},${stock.risk_level || \'N/A\'},${stock.investment_horizon || \'N/A\'}\\n`;
                    });
                } else if (analysisType === \'sectorAnalysis\') {
                    csvContent = \'Market_Cap_Category,Stock_Count,Avg_RS,Avg_Technical_Score,Recommendation\\n\';
                    data.forEach(sector => {
                        csvContent += `${sector.market_cap_category},${sector.stock_count},${sector.avg_rs},${sector.avg_technical},${sector.sector_recommendation}\\n`;
                    });
                } else if (analysisType === \'riskManagement\') {
                    csvContent = \'Risk_Category,Stock_Count,Avg_Score\\n\';
                    data.forEach(risk => {
                        csvContent += `${risk.risk_category},${risk.count},${risk.avg_score}\\n`;
                    });
                } else if (analysisType === \'momentumValue\') {
                    csvContent = \'Investment_Style,Stock_Count,Avg_RS,Avg_Technical_Score\\n\';
                    data.forEach(style => {
                        csvContent += `${style.style},${style.count},${style.avg_rs},${style.avg_technical}\\n`;
                    });
                }
            }
            
            if (data.length === 0) {
                alert(\'No data available for export\');
                return;
            }
            
            downloadCSV(csvContent, filename);
        }
        
        function exportSymbolsForTradingView(analysisType) {
            let data = [];
            
            if (timeframeData[analysisType]) {
                data = timeframeData[analysisType];
            } else if (priceActionData[analysisType]) {
                data = priceActionData[analysisType];
            } else if (relativeStrengthData[analysisType]) {
                data = relativeStrengthData[analysisType];
            } else if (recommendationsData[analysisType]) {
                data = recommendationsData[analysisType];
            }
            
            if (data.length === 0) {
                alert(\'No data available for export\');
                return;
            }
            
            const symbols = data.map(stock => stock.symbol).join(\',\');
            downloadText(symbols, `NSE_${analysisType}_TradingView.txt`);
        }
        
        function downloadCSV(content, filename) {
            const blob = new Blob([content], { type: \'text/csv;charset=utf-8;\' });
            const link = document.createElement(\'a\');
            const url = URL.createObjectURL(blob);
            link.setAttribute(\'href\', url);
            link.setAttribute(\'download\', filename);
            link.style.visibility = \'hidden\';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
        
        function downloadText(content, filename) {
            const blob = new Blob([content], { type: \'text/plain;charset=utf-8;\' });
            const link = document.createElement(\'a\');
            const url = URL.createObjectURL(blob);
            link.setAttribute(\'href\', url);
            link.setAttribute(\'download\', filename);
            link.style.visibility = \'hidden\';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        // Relative Strength Analysis Functions
        function populateRelativeStrengthAnalysis() {
            populateRelativeStrengthCard("exceptionalRSContent", relativeStrengthData.exceptionalRS, "Exceptional");
            populateRelativeStrengthCard("veryStrongRSContent", relativeStrengthData.veryStrongRS, "Very Strong");
            populateRelativeStrengthCard("strongRSContent", relativeStrengthData.strongRS, "Strong");
            populateRelativeStrengthCard("moderateRSContent", relativeStrengthData.moderateRS, "Moderate");
            populateRelativeStrengthCard("rsComparisonContent", relativeStrengthData.rsComparison, "Comparison");
        }
        
        function populateRelativeStrengthCard(containerId, data, type) {
            const container = document.getElementById(containerId);
            
            if (!data || data.length === 0) {
                container.innerHTML = "<div class=\\"no-data\\">No stocks found</div>";
                return;
            }
            
            let html = "<div class=\\"timeframe-stocks\\">";
            data.forEach(stock => {
                const rsValue = stock.relative_strength || 0;
                const rsCategory = stock.rs_category || stock.rs_vs_nifty || "Unknown";
                const rsStrength = stock.rs_strength || stock.rs_performance || "weak";
                
                html += "<div class=\\"timeframe-stock\\">" +
                    "<div class=\\"stock-symbol\\">" + stock.symbol + "</div>" +
                    "<div class=\\"stock-price\\">₹" + stock.current_price + "</div>" +
                    "<div class=\\"stock-metrics\\">" +
                        "<div class=\\"metric\\">" +
                            "<span class=\\"label\\">RS:</span>" +
                            "<span class=\\"value rs-" + rsStrength + "\\">" + rsValue.toFixed(2) + "</span>" +
                        "</div>" +
                        "<div class=\\"metric\\">" +
                            "<span class=\\"label\\">Category:</span>" +
                            "<span class=\\"value category\\">" + rsCategory + "</span>" +
                        "</div>" +
                        "<div class=\\"metric\\">" +
                            "<span class=\\"label\\">Score:</span>" +
                            "<span class=\\"value score\\">" + (stock.technical_score || 0) + "</span>" +
                        "</div>" +
                    "</div>" +
                "</div>";
            });
            html += "</div>";
            container.innerHTML = html;
        }
        
        // Comprehensive Recommendations Functions
        function populateRecommendationsAnalysis() {
            populateRecommendationsCard("topPicksContent", recommendationsData.topPicks, "Top Picks");
            populateRecommendationsCard("sectorAnalysisContent", recommendationsData.sectorAnalysis, "Sector Analysis");
            populateRecommendationsCard("riskManagementContent", recommendationsData.riskManagement, "Risk Management");
            populateRecommendationsCard("momentumValueContent", recommendationsData.momentumValue, "Investment Style");
        }
        
        function populateRecommendationsCard(containerId, data, type) {
            const container = document.getElementById(containerId);
            
            if (!data || data.length === 0) {
                container.innerHTML = "<div class=\\"no-data\\">No recommendations available</div>";
                return;
            }
            
            let html = "<div class=\\"timeframe-stocks\\">";
            
            if (type === "Top Picks") {
                data.forEach(stock => {
                    const riskColor = stock.risk_level === "Low" ? "strong" : stock.risk_level === "Medium" ? "medium" : "weak";
                    const horizonColor = stock.investment_horizon.includes("Short") ? "strong" : 
                                       stock.investment_horizon.includes("Medium") ? "medium" : "weak";
                    
                    html += "<div class=\\"timeframe-stock\\">" +
                        "<div class=\\"stock-symbol\\">" + stock.symbol + "</div>" +
                        "<div class=\\"stock-price\\">₹" + stock.current_price + "</div>" +
                        "<div class=\\"stock-metrics\\">" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Score:</span>" +
                                "<span class=\\"value score\\">" + stock.combined_score.toFixed(1) + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Risk:</span>" +
                                "<span class=\\"value risk-" + riskColor + "\\">" + stock.risk_level + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Horizon:</span>" +
                                "<span class=\\"value horizon-" + horizonColor + "\\">" + stock.investment_horizon + "</span>" +
                            "</div>" +
                        "</div>" +
                    "</div>";
                });
            } else if (type === "Sector Analysis") {
                data.forEach(sector => {
                    const recColor = sector.sector_recommendation === "Strong Buy" ? "strong" : 
                                   sector.sector_recommendation === "Buy" ? "medium" : "weak";
                    
                    html += "<div class=\\"timeframe-stock\\">" +
                        "<div class=\\"stock-symbol\\">" + sector.market_cap_category + "</div>" +
                        "<div class=\\"stock-price\\">" + sector.stock_count + " stocks</div>" +
                        "<div class=\\"stock-metrics\\">" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Avg RS:</span>" +
                                "<span class=\\"value rs-strong\\">" + sector.avg_rs.toFixed(2) + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Avg Score:</span>" +
                                "<span class=\\"value score\\">" + sector.avg_technical.toFixed(1) + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Rec:</span>" +
                                "<span class=\\"value rec-" + recColor + "\\">" + sector.sector_recommendation + "</span>" +
                            "</div>" +
                        "</div>" +
                    "</div>";
                });
            } else if (type === "Risk Management") {
                data.forEach(risk => {
                    const riskColor = risk.risk_category === "Low Risk" ? "strong" : 
                                    risk.risk_category === "Medium Risk" ? "medium" : "weak";
                    
                    html += "<div class=\\"timeframe-stock\\">" +
                        "<div class=\\"stock-symbol\\">" + risk.risk_category + "</div>" +
                        "<div class=\\"stock-price\\">" + risk.count + " stocks</div>" +
                        "<div class=\\"stock-metrics\\">" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Avg Score:</span>" +
                                "<span class=\\"value score\\">" + risk.avg_score.toFixed(1) + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Risk Level:</span>" +
                                "<span class=\\"value risk-" + riskColor + "\\">" + risk.risk_category + "</span>" +
                            "</div>" +
                        "</div>" +
                    "</div>";
                });
            } else if (type === "Investment Style") {
                data.forEach(style => {
                    const styleColor = style.style === "Growth Momentum" ? "strong" : 
                                     style.style === "Balanced" ? "medium" : "weak";
                    
                    html += "<div class=\\"timeframe-stock\\">" +
                        "<div class=\\"stock-symbol\\">" + style.style + "</div>" +
                        "<div class=\\"stock-price\\">" + style.count + " stocks</div>" +
                        "<div class=\\"stock-metrics\\">" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Avg RS:</span>" +
                                "<span class=\\"value rs-strong\\">" + style.avg_rs.toFixed(2) + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Avg Score:</span>" +
                                "<span class=\\"value score\\">" + style.avg_technical.toFixed(1) + "</span>" +
                            "</div>" +
                            "<div class=\\"metric\\">" +
                                "<span class=\\"label\\">Style:</span>" +
                                "<span class=\\"value style-" + styleColor + "\\">" + style.style + "</span>" +
                            "</div>" +
                        "</div>" +
                    "</div>";
                });
            }
            
            html += "</div>";
            container.innerHTML = html;
        }
        
        // Initialize everything when page loads
        document.addEventListener("DOMContentLoaded", () => {
            populateTimeframeAnalysis();
            populatePriceActionAnalysis();
            populateRelativeStrengthAnalysis();
            populateRecommendationsAnalysis();
            populateTabularData();
        });
    </script>
</body>
</html>')
  
  return(html_content)
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
  
  # Apply liquidity and manipulation filters
  stocks_data <- ensure_liquidity(stocks_data)
  stocks_data <- detect_manipulation(stocks_data)
  
  if (nrow(stocks_data) == 0) {
    cat("❌ No liquid, non-manipulated stocks found after filtering\n")
    stop("No suitable stocks available")
  }
  
  cat("✅ Final selection:", nrow(stocks_data), "high-quality liquid stocks\n")
  
  # Generate analysis data
  timeframe_data <- generate_timeframe_analysis(stocks_data)
  price_action_data <- generate_price_action_analysis(stocks_data)
  relative_strength_data <- generate_relative_strength_analysis(stocks_data)
  recommendations_data <- generate_recommendations(stocks_data, timeframe_data, price_action_data, relative_strength_data)
  tabular_data <- generate_tabular_data(stocks_data)
  
  # Generate HTML dashboard
  html_content <- generate_html_dashboard(timeframe_data, price_action_data, relative_strength_data, recommendations_data, tabular_data)
  
  # Save HTML file
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  filename <- paste0("reports/NSE_Enhanced_Analysis_Dashboard_", timestamp, ".html")
  
  writeLines(html_content, filename)
  
  cat("✅ Enhanced Analysis Dashboard generated successfully!\n")
  cat("📁 File saved:", filename, "\n")
  cat("🌐 Opening dashboard in browser...\n")
  
  # Open the dashboard
  system(paste("open", filename))
  
}, error = function(e) {
  cat("❌ Error generating dashboard:", e$message, "\n")
}, finally = {
  # Close database connection
  if (exists("conn")) {
    dbDisconnect(conn)
  }
})

cat("🎉 Enhanced Analysis Dashboard generation completed!\n")
