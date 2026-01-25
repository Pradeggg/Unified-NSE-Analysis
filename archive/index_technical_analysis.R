#!/usr/bin/env Rscript

# Enhanced NSE Index Technical Analysis
# Calculates technical scores for major NSE indices using the same formula as stock analysis

library(dplyr)
library(readr)
library(TTR)
library(lubridate)

print("Starting ENHANCED NSE INDEX TECHNICAL ANALYSIS...")

# Set working directory with error handling
tryCatch({
  setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/')
}, error = function(e) {
  print("Warning: Could not set working directory. Using current directory.")
})

# Store the current directory for output files
output_dir <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/'

# Load index data with enhanced error handling
print("Loading NSE index data...")
tryCatch({
  # Check if file exists
  if(!file.exists('nse_index_data.csv')) {
    stop("nse_index_data.csv not found in current directory")
  }
  
  # Read the file with readr for better handling
  dt_index <- read_csv('nse_index_data.csv', 
                       col_types = cols(.default = "c"),  # Read all as character first
                       locale = locale(encoding = "UTF-8"),
                       show_col_types = FALSE)
  
  # Validate required columns
  required_cols <- c("SYMBOL", "TIMESTAMP", "CLOSE", "OPEN", "HIGH", "LOW", "TOTTRDQTY", "TOTTRDVAL")
  missing_cols <- setdiff(required_cols, names(dt_index))
  if(length(missing_cols) > 0) {
    stop(paste("Missing required columns:", paste(missing_cols, collapse = ", ")))
  }
  
  # Clean and convert data types with validation
  dt_index <- dt_index %>%
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
    filter(!is.na(CLOSE) & !is.na(TIMESTAMP) & CLOSE > 0)
  
  print(paste("Successfully loaded", nrow(dt_index), "clean index records"))
  
}, error = function(e) {
  print(paste("Error loading with readr:", e$message))
  print("Falling back to base R read.csv...")
  
  tryCatch({
    # Fallback to base R with enhanced error handling
    dt_index <- read.csv('nse_index_data.csv', stringsAsFactors = FALSE, fileEncoding = "UTF-8")
    
    # Validate columns
    required_cols <- c("SYMBOL", "TIMESTAMP", "CLOSE", "OPEN", "HIGH", "LOW", "TOTTRDQTY", "TOTTRDVAL")
    missing_cols <- setdiff(required_cols, names(dt_index))
    if(length(missing_cols) > 0) {
      stop(paste("Missing required columns:", paste(missing_cols, collapse = ", ")))
    }
    
    dt_index$TIMESTAMP <- as.Date(dt_index$TIMESTAMP)
    dt_index <- dt_index[!is.na(dt_index$CLOSE) & !is.na(dt_index$TIMESTAMP) & dt_index$CLOSE > 0, ]
    
    print(paste("Successfully loaded", nrow(dt_index), "clean index records using fallback method"))
    
  }, error = function(e2) {
    stop(paste("Failed to load data with both methods:", e2$message))
  })
})

# Get latest date
latest_date <- max(dt_index$TIMESTAMP, na.rm = TRUE)
print(paste("Latest data date:", latest_date))

# Define major indices to analyze
major_indices <- c(
  "Nifty 50",
  "Nifty 500", 
  "Nifty 100",
  "Nifty 200",
  "Nifty Bank",
  "Nifty Next 50",
  "NIFTY MIDCAP 150",
  "NIFTY SMLCAP 250",
  "Nifty IT",
  "Nifty Pharma",
  "Nifty Auto",
  "Nifty FMCG",
  "Nifty Metal",
  "Nifty Realty",
  "Nifty Energy",
  "Nifty Infra"
)

# Function for enhanced technical scoring (same as stock analysis but without relative strength)
calculate_index_tech_score <- function(index_data) {
  if(nrow(index_data) < 50) return(list(score = NA, rsi = NA, trend = NA))
  
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
  
  # For indices, we'll add a momentum score (50 points) instead of relative strength
  momentum_score <- 0
  if(length(prices) >= 50) {
    # Calculate 50-day momentum
    momentum_50d <- (current_price / prices[max(1, length(prices)-50)]) - 1
    
    if(!is.na(momentum_50d)) {
      if(momentum_50d > 0.10) momentum_score <- 50        # 10%+ gain
      else if(momentum_50d > 0.07) momentum_score <- 45   # 7-10% gain
      else if(momentum_50d > 0.05) momentum_score <- 40   # 5-7% gain
      else if(momentum_50d > 0.03) momentum_score <- 35   # 3-5% gain
      else if(momentum_50d > 0.01) momentum_score <- 30   # 1-3% gain
      else if(momentum_50d > 0) momentum_score <- 25      # 0-1% gain
      else if(momentum_50d > -0.01) momentum_score <- 20  # 0-1% loss
      else if(momentum_50d > -0.03) momentum_score <- 15  # 1-3% loss
      else if(momentum_50d > -0.05) momentum_score <- 10  # 3-5% loss
      else if(momentum_50d > -0.07) momentum_score <- 5   # 5-7% loss
      else momentum_score <- 0                             # >7% loss
    }
  }
  
  total_score <- rsi_score + trend_score + momentum_score + volume_score
  
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
  
  return(list(score = total_score, rsi = rsi_val, trend = trend_signal, momentum = momentum_50d))
}

# Process major indices
print("Processing major indices...")
results <- data.frame()
processed_count <- 0
error_count <- 0

for(i in 1:length(major_indices)) {
  index_name <- major_indices[i]
  
  print(paste("Processing index", i, "of", length(major_indices), "-", index_name))
  
  tryCatch({
    # Get historical data for this index (last 200 days)
    index_data <- dt_index %>%
      filter(SYMBOL == index_name & TIMESTAMP >= (latest_date - 200)) %>%
      arrange(TIMESTAMP)
    
    if(nrow(index_data) >= 50) {
      latest_data <- index_data %>% filter(TIMESTAMP == latest_date)
      
      if(nrow(latest_data) > 0) {
        # Calculate enhanced technical score
        tech_result <- calculate_index_tech_score(index_data)
        
        if(!is.na(tech_result$score)) {
          # Create result record
          result <- data.frame(
            RANK = i,
            INDEX_NAME = index_name,
            CURRENT_LEVEL = round(latest_data$CLOSE[1], 2),
            TECHNICAL_SCORE = tech_result$score,
            RSI = round(ifelse(is.na(tech_result$rsi), 0, tech_result$rsi), 1),
            TREND_SIGNAL = tech_result$trend,
            MOMENTUM_50D = round(ifelse(is.na(tech_result$momentum), 0, tech_result$momentum * 100), 2),
            TRADING_VALUE = latest_data$TOTTRDVAL[1],
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
    print(paste("Error processing", index_name, ":", e$message))
  })
}

print(paste("Processing completed. Successfully processed:", processed_count, "indices. Errors:", error_count))

# Sort by technical score
results <- results %>% arrange(desc(TECHNICAL_SCORE))

# Generate comprehensive summary
if(nrow(results) > 0) {
  cat("\n===============================================================================\n")
  cat("COMPREHENSIVE NSE INDEX TECHNICAL ANALYSIS\n")
  cat("Analysis Date:", as.character(latest_date), "\n")
  cat("===============================================================================\n\n")
  
  # Overall summary
  total_analyzed <- nrow(results)
  
  signal_dist <- results %>%
    group_by(TRADING_SIGNAL) %>%
    summarise(COUNT = n(), .groups = 'drop') %>%
    mutate(PERCENTAGE = round(COUNT/total_analyzed*100, 1))
  
  cat("ANALYSIS SUMMARY:\n")
  cat("Total Indices Analyzed:", total_analyzed, "\n\n")
  
  cat("TRADING SIGNALS DISTRIBUTION:\n")
  print(signal_dist)
  cat("\n")
  
  # Top performers
  cat("ALL INDICES RANKED BY TECHNICAL SCORE:\n")
  print(results[, c("INDEX_NAME", "CURRENT_LEVEL", "TECHNICAL_SCORE", "RSI", "MOMENTUM_50D", "TREND_SIGNAL", "TRADING_SIGNAL")])
  
  # Strong buy recommendations
  strong_buys <- results %>% filter(TRADING_SIGNAL == "STRONG_BUY")
  cat("\nSTRONG BUY RECOMMENDATIONS (Score >= 80):\n")
  cat("Total Strong Buys:", nrow(strong_buys), "\n")
  if(nrow(strong_buys) > 0) {
    print(strong_buys[, c("INDEX_NAME", "CURRENT_LEVEL", "TECHNICAL_SCORE", "RSI", "MOMENTUM_50D", "TREND_SIGNAL")])
  }
  
  # Save results with timestamp
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  filename <- paste0(output_dir, "nse_index_technical_analysis_", format(latest_date, "%d%m%Y"), "_", timestamp, ".csv")
  write.csv(results, filename, row.names = FALSE)
  
  # Display enhanced scoring formula explanation
  cat("\nENHANCED INDEX TECHNICAL SCORING FORMULA (100 points):\n")
  cat("• RSI Score (10 points): Optimal range 40-70\n")
  cat("• Price vs SMAs (12 points): Above 10,20,50,100,200 SMAs\n")
  cat("• SMA Crossovers (13 points): 10>20, 20>50, 50>100, 100>200\n")
  cat("• Momentum Score (50 points): 50-day price momentum - MAXIMUM WEIGHT\n")
  cat("• Volume Score (15 points): vs 10-day average\n")
  cat("• Trend Signals: STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, STRONG_BEARISH\n\n")
  
  cat("\nResults saved to:", filename, "\n")
  cat("===============================================================================\n")
  print("Enhanced NSE Index Technical Analysis Completed Successfully!")
  
} else {
  print("No results generated. Please check data quality.")
}
