# =============================================================================
# DETAILED DEBUG BACKTESTING - FIND THE EXACT ISSUE
# =============================================================================

library(dplyr)
library(lubridate)
library(TTR)

# Load NSE data
cat("Loading NSE data...\n")
nse_file <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/nse_sec_full_data.csv"

dt_stocks <- read.csv(nse_file, stringsAsFactors = FALSE)

# Clean and validate data
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

cat("✓ Successfully loaded", nrow(dt_stocks), "clean records\n")

# Test the exact backtesting function logic
test_symbol <- "RELIANCE"
cat("\nTesting backtesting logic for:", test_symbol, "\n")

stock_data <- dt_stocks %>%
  filter(SYMBOL == test_symbol) %>%
  arrange(TIMESTAMP)

cat("Records for", test_symbol, ":", nrow(stock_data), "\n")

if(nrow(stock_data) >= 10) {
  # Test the exact logic from the backtesting function
  LOOKBACK_PERIOD <- 5
  
  cat("Testing signal generation starting from index:", LOOKBACK_PERIOD, "\n")
  
  # Calculate technical indicators
  prices <- stock_data$CLOSE
  volumes <- stock_data$TOTTRDQTY
  
  cat("Price data length:", length(prices), "\n")
  cat("Volume data length:", length(volumes), "\n")
  
  # Test each indicator individually
  cat("\nTesting RSI...\n")
  rsi_values <- tryCatch(RSI(prices, n = 3), error = function(e) {
    cat("RSI error:", e$message, "\n")
    rep(NA, length(prices))
  })
  cat("RSI length:", length(rsi_values), "\n")
  
  cat("\nTesting SMAs...\n")
  sma_3 <- tryCatch(SMA(prices, n = 3), error = function(e) {
    cat("SMA(3) error:", e$message, "\n")
    rep(NA, length(prices))
  })
  sma_5 <- tryCatch(SMA(prices, n = 5), error = function(e) {
    cat("SMA(5) error:", e$message, "\n")
    rep(NA, length(prices))
  })
  sma_7 <- tryCatch(SMA(prices, n = 7), error = function(e) {
    cat("SMA(7) error:", e$message, "\n")
    rep(NA, length(prices))
  })
  
  cat("SMA lengths:", length(sma_3), length(sma_5), length(sma_7), "\n")
  
  cat("\nTesting MACD...\n")
  macd_result <- tryCatch(MACD(prices, nFast = 3, nSlow = 7, nSig = 3), error = function(e) {
    cat("MACD error:", e$message, "\n")
    matrix(rep(NA, length(prices) * 2), ncol = 2, dimnames = list(NULL, c("macd", "signal")))
  })
  cat("MACD dimensions:", dim(macd_result), "\n")
  
  cat("\nTesting Bollinger Bands...\n")
  bb_result <- tryCatch(BBands(prices, n = 5, sd = 2), error = function(e) {
    cat("BB error:", e$message, "\n")
    matrix(rep(NA, length(prices) * 3), ncol = 3, dimnames = list(NULL, c("upper", "middle", "lower")))
  })
  cat("BB dimensions:", dim(bb_result), "\n")
  
  cat("\nTesting Volume SMA...\n")
  vol_sma <- tryCatch(SMA(volumes, n = 5), error = function(e) {
    cat("Volume SMA error:", e$message, "\n")
    rep(NA, length(volumes))
  })
  cat("Volume SMA length:", length(vol_sma), "\n")
  
  # Test signal generation for one specific index
  test_index <- LOOKBACK_PERIOD
  cat("\nTesting signal generation at index:", test_index, "\n")
  
  if(test_index <= length(prices)) {
    current_price <- prices[test_index]
    current_volume <- volumes[test_index]
    
    cat("Current price:", current_price, "\n")
    cat("Current volume:", current_volume, "\n")
    
    # Test each condition
    score <- 0
    
    # RSI signals
    if(!is.na(rsi_values[test_index])) {
      cat("RSI value:", rsi_values[test_index], "\n")
      if(rsi_values[test_index] > 30 && rsi_values[test_index] < 70) {
        score <- score + 10
        cat("RSI score added: 10\n")
      } else if(rsi_values[test_index] > 20 && rsi_values[test_index] < 80) {
        score <- score + 5
        cat("RSI score added: 5\n")
      }
    } else {
      cat("RSI is NA\n")
    }
    
    # Moving average signals
    if(!is.na(sma_3[test_index]) && !is.na(sma_5[test_index]) && current_price > sma_3[test_index] && sma_3[test_index] > sma_5[test_index]) {
      score <- score + 15
      cat("SMA(3,5) score added: 15\n")
    }
    
    if(!is.na(sma_5[test_index]) && !is.na(sma_7[test_index]) && current_price > sma_5[test_index] && sma_5[test_index] > sma_7[test_index]) {
      score <- score + 15
      cat("SMA(5,7) score added: 15\n")
    }
    
    # MACD signals
    if(!is.na(macd_result[test_index, "macd"]) && !is.na(macd_result[test_index, "signal"]) && 
       macd_result[test_index, "macd"] > macd_result[test_index, "signal"]) {
      score <- score + 10
      cat("MACD score added: 10\n")
    }
    
    # Bollinger Bands signals
    if(!is.na(bb_result[test_index, "lower"]) && current_price > bb_result[test_index, "lower"]) {
      score <- score + 5
      cat("BB score added: 5\n")
    }
    
    # Volume signals
    if(!is.na(vol_sma[test_index]) && current_volume > vol_sma[test_index] * 1.2) {
      score <- score + 5
      cat("Volume score added: 5\n")
    }
    
    cat("Final score:", score, "\n")
    
    # Determine signal
    signal <- case_when(
      score >= 50 ~ "STRONG_BUY",
      score >= 35 ~ "BUY",
      score >= 20 ~ "HOLD",
      score >= 10 ~ "WEAK_HOLD",
      TRUE ~ "SELL"
    )
    
    cat("Signal:", signal, "\n")
  } else {
    cat("Test index out of bounds!\n")
  }
}






