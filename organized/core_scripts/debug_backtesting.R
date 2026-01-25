# =============================================================================
# DEBUG BACKTESTING - UNDERSTAND WHY FILES ARE BLANK
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

# Check data for a specific stock
test_symbol <- "RELIANCE"
cat("\nTesting stock:", test_symbol, "\n")

stock_data <- dt_stocks %>%
  filter(SYMBOL == test_symbol) %>%
  arrange(TIMESTAMP)

cat("Records for", test_symbol, ":", nrow(stock_data), "\n")
cat("Date range:", min(stock_data$TIMESTAMP), "to", max(stock_data$TIMESTAMP), "\n")

if(nrow(stock_data) > 0) {
  cat("Sample data:\n")
  print(head(stock_data[, c("SYMBOL", "TIMESTAMP", "CLOSE", "TOTTRDQTY")], 5))
  
  # Test technical indicators
  cat("\nTesting technical indicators...\n")
  prices <- stock_data$CLOSE
  
  # Test RSI
  tryCatch({
    rsi_values <- RSI(prices, n = 3)
    cat("RSI calculation successful. Length:", length(rsi_values), "\n")
    cat("First few RSI values:", head(rsi_values, 5), "\n")
  }, error = function(e) {
    cat("RSI error:", e$message, "\n")
  })
  
  # Test SMA
  tryCatch({
    sma_3 <- SMA(prices, n = 3)
    cat("SMA(3) calculation successful. Length:", length(sma_3), "\n")
    cat("First few SMA values:", head(sma_3, 5), "\n")
  }, error = function(e) {
    cat("SMA error:", e$message, "\n")
  })
  
  # Test MACD
  tryCatch({
    macd_result <- MACD(prices, nFast = 3, nSlow = 7, nSig = 3)
    cat("MACD calculation successful. Dimensions:", dim(macd_result), "\n")
  }, error = function(e) {
    cat("MACD error:", e$message, "\n")
  })
  
  # Test Bollinger Bands
  tryCatch({
    bb_result <- BBands(prices, n = 5, sd = 2)
    cat("Bollinger Bands calculation successful. Dimensions:", dim(bb_result), "\n")
  }, error = function(e) {
    cat("Bollinger Bands error:", e$message, "\n")
  })
}

# Check what stocks have sufficient data
cat("\nChecking stocks with sufficient data...\n")
latest_date <- max(dt_stocks$TIMESTAMP, na.rm = TRUE)
cat("Latest data date:", latest_date, "\n")

latest_stocks <- dt_stocks %>%
  filter(TIMESTAMP == latest_date & !is.na(TOTTRDVAL) & TOTTRDVAL > 0) %>%
  arrange(desc(TOTTRDVAL))

cat("Stocks with data on", latest_date, ":", nrow(latest_stocks), "\n")

# Check first few stocks for data availability
for(i in 1:min(5, nrow(latest_stocks))) {
  symbol <- latest_stocks$SYMBOL[i]
  
  stock_data <- dt_stocks %>%
    filter(SYMBOL == symbol) %>%
    arrange(TIMESTAMP)
  
  cat(symbol, ":", nrow(stock_data), "records\n")
  
  if(nrow(stock_data) >= 10) {
    # Test if technical indicators work
    prices <- stock_data$CLOSE
    tryCatch({
      rsi <- RSI(prices, n = 3)
      sma <- SMA(prices, n = 3)
      cat("  ✓ Technical indicators work\n")
    }, error = function(e) {
      cat("  ✗ Technical indicators fail:", e$message, "\n")
    })
  } else {
    cat("  ✗ Insufficient data\n")
  }
}
