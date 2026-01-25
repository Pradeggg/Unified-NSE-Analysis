#!/usr/bin/env Rscript

# =============================================================================
# TATASTEEL Trend Signal Analysis
# =============================================================================

cat("=== ANALYZING TATASTEEL TREND SIGNAL ===\n")

# Load required libraries
suppressMessages({
  library(dplyr)
  library(TTR)
})

# Load NSE data
cat("Loading NSE data...\n")
dt_stocks <- read.csv("../NSE-index/nse_sec_full_data.csv", stringsAsFactors = FALSE)
dt_stocks$TIMESTAMP <- as.Date(dt_stocks$TIMESTAMP)

# Filter TATASTEEL data
tata_steel_data <- dt_stocks[dt_stocks$SYMBOL == "TATASTEEL", ]
cat("Total TATASTEEL records:", nrow(tata_steel_data), "\n")
cat("Date range:", as.character(min(tata_steel_data$TIMESTAMP)), "to", as.character(max(tata_steel_data$TIMESTAMP)), "\n")

if(nrow(tata_steel_data) >= 200) {
  # Convert prices to numeric
  prices <- as.numeric(tata_steel_data$CLOSE)
  current_price <- tail(prices, 1)
  
  cat("Latest price:", current_price, "\n")
  cat("Price data points:", length(prices), "\n")
  
  # Calculate SMAs
  cat("\n=== SMA CALCULATIONS ===\n")
  sma_10 <- tail(SMA(prices, n = 10), 1)
  sma_20 <- tail(SMA(prices, n = 20), 1)
  sma_50 <- tail(SMA(prices, n = 50), 1)
  sma_100 <- tail(SMA(prices, n = 100), 1)
  sma_200 <- tail(SMA(prices, n = 200), 1)
  
  cat("Current price:", current_price, "\n")
  cat("SMA 10:", round(sma_10, 2), "\n")
  cat("SMA 20:", round(sma_20, 2), "\n")
  cat("SMA 50:", round(sma_50, 2), "\n")
  cat("SMA 100:", round(sma_100, 2), "\n")
  cat("SMA 200:", round(sma_200, 2), "\n")
  
  # Price vs SMA Analysis
  cat("\n=== PRICE VS SMA ANALYSIS ===\n")
  price_above_sma10 <- current_price > sma_10
  price_above_sma20 <- current_price > sma_20
  price_above_sma50 <- current_price > sma_50
  price_above_sma100 <- current_price > sma_100
  price_above_sma200 <- current_price > sma_200
  
  cat("Price > SMA 10:", price_above_sma10, "\n")
  cat("Price > SMA 20:", price_above_sma20, "\n")
  cat("Price > SMA 50:", price_above_sma50, "\n")
  cat("Price > SMA 100:", price_above_sma100, "\n")
  cat("Price > SMA 200:", price_above_sma200, "\n")
  
  # SMA Crossover Analysis
  cat("\n=== SMA CROSSOVER ANALYSIS ===\n")
  sma10_above_sma20 <- sma_10 > sma_20
  sma20_above_sma50 <- sma_20 > sma_50
  sma50_above_sma100 <- sma_50 > sma_100
  sma100_above_sma200 <- sma_100 > sma_200
  
  cat("SMA 10 > SMA 20:", sma10_above_sma20, "\n")
  cat("SMA 20 > SMA 50:", sma20_above_sma20, "\n")
  cat("SMA 50 > SMA 100:", sma50_above_sma100, "\n")
  cat("SMA 100 > SMA 200:", sma100_above_sma200, "\n")
  
  # Calculate trend signal
  cat("\n=== TREND SIGNAL CALCULATION ===\n")
  bullish_count <- 0
  bearish_count <- 0
  
  # Price vs SMAs
  if(price_above_sma10) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(price_above_sma20) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(price_above_sma50) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(price_above_sma100) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(price_above_sma200) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  
  # SMA Crossovers
  if(sma10_above_sma20) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(sma20_above_sma50) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(sma50_above_sma100) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  if(sma100_above_sma200) bullish_count <- bullish_count + 1 else bearish_count <- bearish_count + 1
  
  cat("Bullish signals:", bullish_count, "\n")
  cat("Bearish signals:", bearish_count, "\n")
  
  # Final trend determination
  cat("\n=== FINAL TREND DETERMINATION ===\n")
  if(bullish_count >= 3) {
    cat("TREND: STRONG_BULLISH\n")
  } else if(bullish_count >= 2) {
    cat("TREND: BULLISH\n")
  } else if(bearish_count >= 3) {
    cat("TREND: STRONG_BEARISH\n")
  } else if(bearish_count >= 2) {
    cat("TREND: BEARISH\n")
  } else {
    cat("TREND: NEUTRAL\n")
  }
  
  # Explain the reasoning
  cat("\n=== EXPLANATION OF BEARISH SIGNAL ===\n")
  cat("Despite recent price gains, TATASTEEL shows BEARISH trend due to:\n")
  
  if(!price_above_sma200) cat("• Price below 200-day SMA (long-term bearish)\n")
  if(!price_above_sma100) cat("• Price below 100-day SMA (medium-term bearish)\n")
  if(!price_above_sma50) cat("• Price below 50-day SMA (short-term bearish)\n")
  if(!sma50_above_sma100) cat("• 50-day SMA below 100-day SMA (bearish crossover)\n")
  if(!sma100_above_sma200) cat("• 100-day SMA below 200-day SMA (long-term bearish crossover)\n")
  
  cat("\nRecent gains may be a temporary bounce within a longer-term downtrend.\n")
  cat("Technical indicators suggest caution despite positive price action.\n")
  
} else {
  cat("Insufficient data for analysis\n")
}
