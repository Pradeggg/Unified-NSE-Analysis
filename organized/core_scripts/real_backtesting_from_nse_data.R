# =============================================================================
# REAL BACKTESTING FROM NSE DATA - HISTORICAL PERFORMANCE ANALYSIS
# =============================================================================
# This script performs REAL historical backtesting using actual NSE data
# instead of simulated performance metrics

library(dplyr)
library(lubridate)
library(TTR)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Backtesting parameters
BACKTEST_DAYS <- 15   # Reduced to 15 days (about 2 weeks)
LOOKBACK_PERIOD <- 5   # Reduced to 5 days for signal generation
HOLDING_PERIOD <- 3    # Reduced to 3 days to hold a position
STOP_LOSS_PCT <- 0.05  # 5% stop loss
TAKE_PROFIT_PCT <- 0.15  # 15% take profit

# =============================================================================
# FUNCTIONS
# =============================================================================

# Function to load NSE data directly
load_nse_data_directly <- function() {
  cat("Loading NSE data directly from nse_sec_full_data.csv...\n")
  
  # Check if file exists
  nse_file <- "nse_sec_full_data.csv"
  if(!file.exists(nse_file)) {
    # Try alternative paths
    possible_paths <- c(
      "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/nse_sec_full_data.csv",
      "@NSE-index/nse_sec_full_data.csv",
      "../@NSE-index/nse_sec_full_data.csv",
      "NSE@NSE-index/nse_sec_full_data.csv",
      "../NSE@NSE-index/nse_sec_full_data.csv",
      "../NSE-index/nse_sec_full_data.csv",
      "data/nse_sec_full_data.csv",
      "organized/data/nse_sec_full_data.csv"
    )
    
    for(path in possible_paths) {
      if(file.exists(path)) {
        nse_file <- path
        break
      }
    }
  }
  
  if(!file.exists(nse_file)) {
    stop("nse_sec_full_data.csv not found. Please ensure the file is available.")
  }
  
  cat("Loading data from:", nse_file, "\n")
  
  # Load the data
  tryCatch({
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
    return(dt_stocks)
    
  }, error = function(e) {
    stop(paste("Error loading NSE data:", e$message))
  })
}

# Function to generate trading signals based on technical indicators
generate_trading_signals <- function(stock_data) {
  if(nrow(stock_data) < LOOKBACK_PERIOD) return(NULL)
  
  signals <- data.frame()
  
  # Calculate technical indicators with error handling
  prices <- stock_data$CLOSE
  volumes <- stock_data$TOTTRDQTY
  
  # RSI
  rsi_values <- tryCatch(RSI(prices, n = 3), error = function(e) rep(NA, length(prices)))  # Reduced to 3 days
  
  # Moving averages
  sma_3 <- tryCatch(SMA(prices, n = 3), error = function(e) rep(NA, length(prices)))   # Reduced to 3 days
  sma_5 <- tryCatch(SMA(prices, n = 5), error = function(e) rep(NA, length(prices)))
  sma_7 <- tryCatch(SMA(prices, n = 7), error = function(e) rep(NA, length(prices)))  # Reduced to 7 days
  
  # MACD
  macd_result <- tryCatch(MACD(prices, nFast = 3, nSlow = 7, nSig = 3), error = function(e) {  # Very short periods
    matrix(rep(NA, length(prices) * 2), ncol = 2, dimnames = list(NULL, c("macd", "signal")))
  })
  macd_line <- macd_result[, "macd"]
  macd_signal <- macd_result[, "signal"]
  
  # Bollinger Bands
  bb_result <- tryCatch(BBands(prices, n = 5, sd = 2), error = function(e) {  # Reduced to 5 days
    matrix(rep(NA, length(prices) * 4), ncol = 4, dimnames = list(NULL, c("dn", "mavg", "up", "pctB")))
  })
  bb_upper <- bb_result[, "up"]
  bb_lower <- bb_result[, "dn"]
  
  # Volume moving average
  vol_sma <- tryCatch(SMA(volumes, n = 5), error = function(e) rep(NA, length(volumes)))  # Reduced to 5 days
  
  # Generate signals for each day
  for(i in LOOKBACK_PERIOD:nrow(stock_data)) {
    current_price <- prices[i]
    current_volume <- volumes[i]
    
    # Technical score calculation
    score <- 0
    
    # RSI signals
    if(!is.na(rsi_values[i])) {
      if(rsi_values[i] > 30 && rsi_values[i] < 70) score <- score + 10
      else if(rsi_values[i] > 20 && rsi_values[i] < 80) score <- score + 5
    }
    
    # Moving average signals
    if(!is.na(sma_3[i]) && !is.na(sma_5[i]) && current_price > sma_3[i] && sma_3[i] > sma_5[i]) {
      score <- score + 15
    }
    
    if(!is.na(sma_5[i]) && !is.na(sma_7[i]) && current_price > sma_5[i] && sma_5[i] > sma_7[i]) {
      score <- score + 15
    }
    
    # MACD signals
    if(!is.na(macd_line[i]) && !is.na(macd_signal[i]) && macd_line[i] > macd_signal[i]) {
      score <- score + 10
    }
    
    # Bollinger Bands signals
    if(!is.na(bb_lower[i]) && current_price > bb_lower[i]) {
      score <- score + 5
    }
    
    # Volume signals
    if(!is.na(vol_sma[i]) && current_volume > vol_sma[i] * 1.2) {
      score <- score + 5
    }
    
    # Determine signal
    signal <- case_when(
      score >= 50 ~ "STRONG_BUY",
      score >= 35 ~ "BUY",
      score >= 20 ~ "HOLD",
      score >= 10 ~ "WEAK_HOLD",
      TRUE ~ "SELL"
    )
    
    # Add signal to dataframe
    signal_row <- data.frame(
      SYMBOL = stock_data$SYMBOL[i],
      TIMESTAMP = stock_data$TIMESTAMP[i],
      PRICE = current_price,
      VOLUME = current_volume,
      TECHNICAL_SCORE = score,
      RSI = ifelse(is.na(rsi_values[i]), 0, rsi_values[i]),
      SMA_3 = ifelse(is.na(sma_3[i]), 0, sma_3[i]),
      SMA_5 = ifelse(is.na(sma_5[i]), 0, sma_5[i]),
      SMA_7 = ifelse(is.na(sma_7[i]), 0, sma_7[i]),
      MACD_LINE = ifelse(is.na(macd_line[i]), 0, macd_line[i]),
      MACD_SIGNAL = ifelse(is.na(macd_signal[i]), 0, macd_signal[i]),
      BB_UPPER = ifelse(is.na(bb_upper[i]), 0, bb_upper[i]),
      BB_LOWER = ifelse(is.na(bb_lower[i]), 0, bb_lower[i]),
      VOLUME_SMA = ifelse(is.na(vol_sma[i]), 0, vol_sma[i]),
      SIGNAL = signal,
      stringsAsFactors = FALSE
    )
    
    signals <- rbind(signals, signal_row)
  }
  
  return(signals)
}

# Function to execute trades based on signals
execute_trades <- function(stock_data, signals) {
  trades <- data.frame()
  
  if(nrow(signals) == 0) return(trades)
  
  # Get buy signals
  buy_signals <- signals %>%
    filter(SIGNAL %in% c("STRONG_BUY", "BUY")) %>%
    arrange(TIMESTAMP)
  
  if(nrow(buy_signals) == 0) return(trades)
  
  # Execute trades for each buy signal
  for(i in 1:nrow(buy_signals)) {
    buy_signal <- buy_signals[i, ]
    buy_date <- buy_signal$TIMESTAMP
    buy_price <- buy_signal$PRICE
    
    # Find the corresponding data point
    buy_index <- which(stock_data$TIMESTAMP == buy_date)
    if(length(buy_index) == 0) next
    
    # Look ahead for exit conditions
    exit_price <- buy_price
    exit_date <- buy_date
    exit_reason <- "HOLDING_PERIOD"
    
    # Check for stop loss, take profit, or holding period
    for(j in (buy_index + 1):min(buy_index + HOLDING_PERIOD, nrow(stock_data))) {
      if(j > nrow(stock_data)) break
      
      current_price <- stock_data$CLOSE[j]
      current_date <- stock_data$TIMESTAMP[j]
      
      # Check stop loss
      if(current_price <= buy_price * (1 - STOP_LOSS_PCT)) {
        exit_price <- current_price
        exit_date <- current_date
        exit_reason <- "STOP_LOSS"
        break
      }
      
      # Check take profit
      if(current_price >= buy_price * (1 + TAKE_PROFIT_PCT)) {
        exit_price <- current_price
        exit_date <- current_date
        exit_reason <- "TAKE_PROFIT"
        break
      }
      
      # Update exit price for holding period
      exit_price <- current_price
      exit_date <- current_date
    }
    
    # Calculate trade metrics
    trade_return <- (exit_price - buy_price) / buy_price
    trade_days <- as.numeric(exit_date - buy_date)
    
    # Create trade record
    trade <- data.frame(
      SYMBOL = buy_signal$SYMBOL,
      BUY_DATE = buy_date,
      BUY_PRICE = buy_price,
      EXIT_DATE = exit_date,
      EXIT_PRICE = exit_price,
      EXIT_REASON = exit_reason,
      TRADE_RETURN = trade_return,
      TRADE_DAYS = trade_days,
      TECHNICAL_SCORE = buy_signal$TECHNICAL_SCORE,
      RSI = buy_signal$RSI,
      SIGNAL = buy_signal$SIGNAL,
      stringsAsFactors = FALSE
    )
    
    trades <- rbind(trades, trade)
  }
  
  return(trades)
}

# Function to calculate performance metrics for a stock
calculate_stock_performance <- function(trades, stock_data) {
  if(nrow(trades) == 0) {
    return(data.frame(
      SYMBOL = unique(stock_data$SYMBOL),
      TOTAL_TRADES = 0,
      WINNING_TRADES = 0,
      LOSING_TRADES = 0,
      WIN_RATE = 0,
      TOTAL_RETURN = 0,
      AVG_RETURN = 0,
      MAX_RETURN = 0,
      MIN_RETURN = 0,
      AVG_TRADE_DAYS = 0,
      SHARPE_RATIO = 0,
      MAX_DRAWDOWN = 0,
      PROFIT_FACTOR = 0,
      stringsAsFactors = FALSE
    ))
  }
  
  # Basic metrics
  total_trades <- nrow(trades)
  winning_trades <- sum(trades$TRADE_RETURN > 0, na.rm = TRUE)
  losing_trades <- sum(trades$TRADE_RETURN <= 0, na.rm = TRUE)
  win_rate <- winning_trades / total_trades
  
  # Return metrics
  total_return <- sum(trades$TRADE_RETURN, na.rm = TRUE)
  avg_return <- mean(trades$TRADE_RETURN, na.rm = TRUE)
  max_return <- max(trades$TRADE_RETURN, na.rm = TRUE)
  min_return <- min(trades$TRADE_RETURN, na.rm = TRUE)
  avg_trade_days <- mean(trades$TRADE_DAYS, na.rm = TRUE)
  
  # Risk metrics
  returns_std <- sd(trades$TRADE_RETURN, na.rm = TRUE)
  sharpe_ratio <- ifelse(returns_std > 0, avg_return / returns_std, 0)
  
  # Calculate drawdown
  cumulative_returns <- cumsum(trades$TRADE_RETURN)
  running_max <- cummax(cumulative_returns)
  drawdowns <- cumulative_returns - running_max
  max_drawdown <- min(drawdowns, na.rm = TRUE)
  
  # Profit factor
  gross_profit <- sum(trades$TRADE_RETURN[trades$TRADE_RETURN > 0], na.rm = TRUE)
  gross_loss <- abs(sum(trades$TRADE_RETURN[trades$TRADE_RETURN <= 0], na.rm = TRUE))
  profit_factor <- ifelse(gross_loss > 0, gross_profit / gross_loss, 0)
  
  # Create performance summary
  performance <- data.frame(
    SYMBOL = unique(stock_data$SYMBOL),
    TOTAL_TRADES = total_trades,
    WINNING_TRADES = winning_trades,
    LOSING_TRADES = losing_trades,
    WIN_RATE = win_rate,
    TOTAL_RETURN = total_return,
    AVG_RETURN = avg_return,
    MAX_RETURN = max_return,
    MIN_RETURN = min_return,
    AVG_TRADE_DAYS = avg_trade_days,
    SHARPE_RATIO = sharpe_ratio,
    MAX_DRAWDOWN = max_drawdown,
    PROFIT_FACTOR = profit_factor,
    stringsAsFactors = FALSE
  )
  
  return(performance)
}

# Function to calculate confidence score based on real performance
calculate_real_confidence_score <- function(performance, trades) {
  if(nrow(trades) == 0) return(0)
  
  # Base confidence on actual performance metrics
  confidence_factors <- c()
  
  # Win rate factor (0-1)
  win_rate_factor <- performance$WIN_RATE
  confidence_factors <- c(confidence_factors, win_rate_factor)
  
  # Return factor (0-1, capped at 0.5 for very high returns)
  return_factor <- min(abs(performance$TOTAL_RETURN), 0.5) / 0.5
  confidence_factors <- c(confidence_factors, return_factor)
  
  # Sharpe ratio factor (0-1, good Sharpe is > 1)
  sharpe_factor <- min(max(performance$SHARPE_RATIO, 0), 2) / 2
  confidence_factors <- c(confidence_factors, sharpe_factor)
  
  # Profit factor (0-1, good profit factor is > 1.5)
  profit_factor <- min(performance$PROFIT_FACTOR / 1.5, 1)
  confidence_factors <- c(confidence_factors, profit_factor)
  
  # Trade count factor (more trades = more confidence, up to 10 trades)
  trade_factor <- min(performance$TOTAL_TRADES / 10, 1)
  confidence_factors <- c(confidence_factors, trade_factor)
  
  # Calculate weighted average
  weights <- c(0.3, 0.25, 0.2, 0.15, 0.1)  # Win rate, return, Sharpe, profit factor, trade count
  confidence_score <- sum(confidence_factors * weights, na.rm = TRUE)
  
  return(confidence_score)
}

# Function to get stocks with sufficient data for backtesting
get_stocks_for_backtesting <- function(dt_stocks, min_days = 10) {  # Reduced to 10 days minimum
  cat("Identifying stocks with sufficient data for real backtesting...\n")
  
  # Get latest date
  latest_date <- max(dt_stocks$TIMESTAMP, na.rm = TRUE)
  cat("Latest data date:", latest_date, "\n")
  
  # Get stocks with data on latest date
  latest_stocks <- dt_stocks %>%
    filter(TIMESTAMP == latest_date & !is.na(TOTTRDVAL) & TOTTRDVAL > 0) %>%
    arrange(desc(TOTTRDVAL))
  
  cat("Stocks with data on", latest_date, ":", nrow(latest_stocks), "\n")
  
  # Filter stocks with sufficient historical data
  stocks_with_sufficient_data <- c()
  
  for(i in 1:nrow(latest_stocks)) {
    symbol <- latest_stocks$SYMBOL[i]
    
    # Get historical data for this stock
    stock_data <- dt_stocks %>%
      filter(SYMBOL == symbol) %>%
      arrange(TIMESTAMP)
    
    if(nrow(stock_data) >= min_days) {
      stocks_with_sufficient_data <- c(stocks_with_sufficient_data, symbol)
    }
    
    if(i %% 100 == 0) {
      cat("Processed", i, "of", nrow(latest_stocks), "stocks. Found", length(stocks_with_sufficient_data), "with sufficient data.\n")
    }
  }
  
  cat("✓ Found", length(stocks_with_sufficient_data), "stocks with sufficient data for real backtesting\n")
  return(stocks_with_sufficient_data)
}

# Function to run real backtesting for a single stock
run_real_backtesting_for_stock <- function(symbol, dt_stocks) {
  tryCatch({
    # Get historical data for this stock
    stock_data <- dt_stocks %>%
      filter(SYMBOL == symbol) %>%
      arrange(TIMESTAMP)
    
    if(nrow(stock_data) < 10) {  # Reduced to 10 days minimum
      return(NULL)
    }
    
    # Generate trading signals
    signals <- generate_trading_signals(stock_data)
    
    if(is.null(signals) || nrow(signals) == 0) {
      return(NULL)
    }
    
    # Execute trades
    trades <- execute_trades(stock_data, signals)
    
    if(nrow(trades) == 0) {
      return(NULL)
    }
    
    # Calculate performance metrics
    performance <- calculate_stock_performance(trades, stock_data)
    
    # Calculate real confidence score
    confidence_score <- calculate_real_confidence_score(performance, trades)
    
    # Add confidence score to performance
    performance$CONFIDENCE_SCORE <- confidence_score
    
    # Add current price and technical indicators
    latest_data <- stock_data %>% filter(TIMESTAMP == max(TIMESTAMP))
    if(nrow(latest_data) > 0) {
      performance$CURRENT_PRICE <- latest_data$CLOSE[1]
      performance$CURRENT_VOLUME <- latest_data$TOTTRDQTY[1]
      
      # Calculate current technical indicators
      prices <- stock_data$CLOSE
      rsi_current <- tail(RSI(prices, n = 14), 1)
      sma_20_current <- tail(SMA(prices, n = 20), 1)
      
      performance$CURRENT_RSI <- ifelse(is.na(rsi_current), 0, rsi_current)
      performance$CURRENT_SMA_20 <- ifelse(is.na(sma_20_current), 0, sma_20_current)
    }
    
    # Add analysis date
    performance$ANALYSIS_DATE <- max(dt_stocks$TIMESTAMP, na.rm = TRUE)
    
    return(list(
      performance = performance,
      trades = trades,
      signals = signals
    ))
    
  }, error = function(e) {
    cat("Error backtesting", symbol, ":", e$message, "\n")
    return(NULL)
  })
}

# Function to save real backtesting results
save_real_backtesting_results <- function(backtesting_results) {
  cat("Saving real backtesting results...\n")
  
  # Create output directory
  output_dir <- "organized/backtesting_results/"
  if(!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  # Extract performance data
  performance_data <- do.call(rbind, lapply(backtesting_results, function(x) x$performance))
  
  # Extract all trades
  all_trades <- do.call(rbind, lapply(backtesting_results, function(x) x$trades))
  
  # Extract all signals
  all_signals <- do.call(rbind, lapply(backtesting_results, function(x) x$signals))
  
  # Generate timestamp
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Save files
  performance_file <- paste0(output_dir, "real_backtesting_performance_", timestamp, ".csv")
  trades_file <- paste0(output_dir, "real_backtesting_trades_", timestamp, ".csv")
  signals_file <- paste0(output_dir, "real_backtesting_signals_", timestamp, ".csv")
  
  write.csv(performance_data, performance_file, row.names = FALSE)
  write.csv(all_trades, trades_file, row.names = FALSE)
  write.csv(all_signals, signals_file, row.names = FALSE)
  
  cat("✓ Performance data saved to:", performance_file, "\n")
  cat("✓ Trades data saved to:", trades_file, "\n")
  cat("✓ Signals data saved to:", signals_file, "\n")
  
  return(list(
    performance_file = performance_file,
    trades_file = trades_file,
    signals_file = signals_file
  ))
}

# Function to print comprehensive summary
print_real_backtesting_summary <- function(backtesting_results, saved_files) {
  cat("\n" , "=", 80, "\n")
  cat("REAL BACKTESTING RESULTS SUMMARY\n")
  cat("=", 80, "\n")
  
  # Extract performance data
  if(length(backtesting_results) == 0) {
    cat("No backtesting results to summarize - no stocks had sufficient data for real backtesting\n")
    return()
  }
  
  performance_data <- do.call(rbind, lapply(backtesting_results, function(x) x$performance))
  
  if(is.null(performance_data) || nrow(performance_data) == 0) {
    cat("No backtesting results to summarize - no stocks had sufficient data for real backtesting\n")
    return()
  }
  
  # Overall statistics
  cat("\n📊 OVERALL STATISTICS:\n")
  cat("Total Stocks Analyzed:", nrow(performance_data), "\n")
  cat("Total Trades Executed:", sum(performance_data$TOTAL_TRADES, na.rm = TRUE), "\n")
  cat("Average Trades per Stock:", round(mean(performance_data$TOTAL_TRADES, na.rm = TRUE), 1), "\n")
  
  # Performance metrics
  cat("\n📈 PERFORMANCE METRICS:\n")
  cat("Average Win Rate:", round(mean(performance_data$WIN_RATE, na.rm = TRUE) * 100, 1), "%\n")
  cat("Average Total Return:", round(mean(performance_data$TOTAL_RETURN, na.rm = TRUE) * 100, 1), "%\n")
  cat("Average Return per Trade:", round(mean(performance_data$AVG_RETURN, na.rm = TRUE) * 100, 1), "%\n")
  cat("Average Sharpe Ratio:", round(mean(performance_data$SHARPE_RATIO, na.rm = TRUE), 2), "\n")
  cat("Average Profit Factor:", round(mean(performance_data$PROFIT_FACTOR, na.rm = TRUE), 2), "\n")
  
  # Confidence analysis
  cat("\n🎯 CONFIDENCE ANALYSIS:\n")
  cat("Average Confidence Score:", round(mean(performance_data$CONFIDENCE_SCORE, na.rm = TRUE) * 100, 1), "%\n")
  cat("High Confidence Stocks (≥70%):", sum(performance_data$CONFIDENCE_SCORE >= 0.7, na.rm = TRUE), "\n")
  cat("Very High Confidence Stocks (≥80%):", sum(performance_data$CONFIDENCE_SCORE >= 0.8, na.rm = TRUE), "\n")
  
  # Top performers
  cat("\n🏆 TOP 10 PERFORMERS BY TOTAL RETURN:\n")
  top_return <- performance_data %>%
    arrange(desc(TOTAL_RETURN)) %>%
    head(10) %>%
    select(SYMBOL, TOTAL_RETURN, WIN_RATE, TOTAL_TRADES, CONFIDENCE_SCORE)
  
  print(top_return)
  
  cat("\n🏆 TOP 10 PERFORMERS BY CONFIDENCE SCORE:\n")
  top_confidence <- performance_data %>%
    arrange(desc(CONFIDENCE_SCORE)) %>%
    head(10) %>%
    select(SYMBOL, CONFIDENCE_SCORE, TOTAL_RETURN, WIN_RATE, TOTAL_TRADES)
  
  print(top_confidence)
  
  cat("\n💾 FILES GENERATED:\n")
  cat("Performance Data:", saved_files$performance_file, "\n")
  cat("Trades Data:", saved_files$trades_file, "\n")
  cat("Signals Data:", saved_files$signals_file, "\n")
  
  cat("\n" , "=", 80, "\n")
  cat("✅ Real backtesting from NSE data completed successfully!\n")
  cat("This analysis uses ACTUAL historical performance, not simulated metrics.\n")
  cat("Check the organized/backtesting_results/ directory for all results.\n")
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

cat("Running REAL backtesting from NSE data...\n")
cat("============================================================\n")
cat("This script performs ACTUAL historical backtesting using real NSE data.\n")
cat("No simulated metrics - all results are based on real trading performance.\n")
cat("============================================================\n")

# Step 1: Load NSE data directly
dt_stocks <- load_nse_data_directly()

# Step 2: Get stocks with sufficient data
stocks_for_backtesting <- get_stocks_for_backtesting(dt_stocks)

# Step 3: Run real backtesting for each stock
cat("\nRunning real backtesting analysis...\n")
backtesting_results <- list()
processed_count <- 0

for(i in 1:length(stocks_for_backtesting)) {
  symbol <- stocks_for_backtesting[i]
  
  if(i %% 50 == 1) {
    cat("Processing stock", i, "of", length(stocks_for_backtesting), "-", symbol, "\n")
  }
  
  result <- run_real_backtesting_for_stock(symbol, dt_stocks)
  
  if(!is.null(result)) {
    backtesting_results[[length(backtesting_results) + 1]] <- result
    processed_count <- processed_count + 1
  }
}

cat("✓ Successfully completed real backtesting for", processed_count, "stocks\n")

# Step 4: Save results
saved_files <- save_real_backtesting_results(backtesting_results)

# Step 5: Print comprehensive summary
print_real_backtesting_summary(backtesting_results, saved_files)

cat("\n🎯 NEXT STEPS:\n")
cat("1. Real backtesting results are now available in CSV format\n")
cat("2. These results contain ACTUAL historical performance, not simulations\n")
cat("3. You can now integrate these real results into the main analysis script\n")
cat("4. Use the real_backtesting_performance_*.csv file for integration\n")
