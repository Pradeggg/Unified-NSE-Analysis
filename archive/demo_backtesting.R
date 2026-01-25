# =============================================================================
# BACKTESTING ENGINE DEMONSTRATION
# =============================================================================
# This script demonstrates the backtesting engine functionality with sample data

library(dplyr)
library(lubridate)

# =============================================================================
# SAMPLE DATA CREATION
# =============================================================================

# Create sample stock data
create_sample_stock_data <- function() {
  # Generate sample data for 5 stocks over 100 days
  stocks <- c("RELIANCE", "TCS", "HDFC", "INFY", "ICICIBANK")
  dates <- seq(as.Date("2024-01-01"), as.Date("2024-05-10"), by = "day")
  
  stock_data <- data.frame()
  
  for(stock in stocks) {
    # Generate realistic price movements
    base_price <- runif(1, 100, 1000)
    prices <- base_price
    
    for(i in 2:length(dates)) {
      # Add some random walk with trend
      change <- rnorm(1, 0.001, 0.02)  # Small daily change
      prices[i] <- prices[i-1] * (1 + change)
    }
    
    # Create OHLC data
    for(i in 1:length(dates)) {
      high <- prices[i] * (1 + abs(rnorm(1, 0, 0.01)))
      low <- prices[i] * (1 - abs(rnorm(1, 0, 0.01)))
      open <- prices[i] * (1 + rnorm(1, 0, 0.005))
      close <- prices[i]
      volume <- round(runif(1, 1000000, 10000000))
      
      stock_data <- rbind(stock_data, data.frame(
        SYMBOL = stock,
        TIMESTAMP = dates[i],
        OPEN = open,
        HIGH = high,
        LOW = low,
        CLOSE = close,
        VOLUME = volume,
        stringsAsFactors = FALSE
      ))
    }
  }
  
  return(stock_data)
}

# Create sample trading signals
create_sample_signals <- function(stock_data) {
  signals <- data.frame()
  
  for(stock in unique(stock_data$SYMBOL)) {
    stock_subset <- stock_data %>%
      filter(SYMBOL == stock) %>%
      arrange(TIMESTAMP)
    
    # Generate simple signals based on price movement
    for(i in 20:nrow(stock_subset)) {
      current_price <- stock_subset$CLOSE[i]
      prev_price <- stock_subset$CLOSE[i-1]
      price_change <- (current_price - prev_price) / prev_price
      
      # Simple signal logic
      if(price_change > 0.02) {  # 2% gain
        signal <- "BUY"
      } else if(price_change < -0.02) {  # 2% loss
        signal <- "SELL"
      } else {
        signal <- "HOLD"
      }
      
      if(signal != "HOLD") {
        signals <- rbind(signals, data.frame(
          SYMBOL = stock,
          TIMESTAMP = stock_subset$TIMESTAMP[i],
          TRADING_SIGNAL = signal,
          RSI = 50 + rnorm(1, 0, 10),
          MOMENTUM_50D = price_change * 10,
          VOLUME_RATIO = 1.0,
          stringsAsFactors = FALSE
        ))
      }
    }
  }
  
  return(signals)
}

# =============================================================================
# SIMPLIFIED BACKTESTING ENGINE
# =============================================================================

SimpleBacktestingEngine <- setRefClass("SimpleBacktestingEngine",
  fields = list(
    data = "data.frame",
    signals = "data.frame",
    results = "data.frame"
  ),
  
  methods = list(
    
    initialize = function(stock_data, trading_signals) {
      data <<- stock_data
      signals <<- trading_signals
      results <<- data.frame()
    },
    
    # Execute trades based on signals
    execute_trades = function(stock_data, signals) {
      trades <- data.frame()
      position <- NULL
      entry_price <- 0
      entry_date <- NULL
      
      for(i in 1:nrow(stock_data)) {
        current_data <- stock_data[i, ]
        current_signal <- signals %>%
          filter(SYMBOL == current_data$SYMBOL, 
                 TIMESTAMP <= current_data$TIMESTAMP) %>%
          arrange(desc(TIMESTAMP)) %>%
          head(1)
        
        if(nrow(current_signal) == 0) next
        
        # Check for entry signal
        if(is.null(position) && current_signal$TRADING_SIGNAL == "BUY") {
          position <- "LONG"
          entry_price <- current_data$CLOSE
          entry_date <- current_data$TIMESTAMP
        }
        
        # Check for exit signal
        else if(!is.null(position) && current_signal$TRADING_SIGNAL == "SELL") {
          exit_price <- current_data$CLOSE
          profit <- (exit_price - entry_price) / entry_price
          
          trade <- data.frame(
            SYMBOL = current_data$SYMBOL,
            ENTRY_DATE = entry_date,
            EXIT_DATE = current_data$TIMESTAMP,
            ENTRY_PRICE = entry_price,
            EXIT_PRICE = exit_price,
            POSITION = position,
            PROFIT = profit,
            HOLDING_DAYS = as.numeric(difftime(current_data$TIMESTAMP, entry_date, units = "days")),
            stringsAsFactors = FALSE
          )
          
          trades <- rbind(trades, trade)
          position <- NULL
          entry_price <- 0
          entry_date <- NULL
        }
      }
      
      return(trades)
    },
    
    # Calculate performance metrics
    calculate_performance_metrics = function(trades) {
      if(nrow(trades) == 0) {
        return(list(
          win_rate = 0,
          total_return = 0,
          avg_return = 0,
          total_trades = 0,
          profitable_trades = 0
        ))
      }
      
      winning_trades <- trades[trades$PROFIT > 0, ]
      
      metrics <- list(
        win_rate = nrow(winning_trades) / nrow(trades),
        total_return = sum(trades$PROFIT, na.rm = TRUE),
        avg_return = mean(trades$PROFIT, na.rm = TRUE),
        total_trades = nrow(trades),
        profitable_trades = nrow(winning_trades)
      )
      
      return(metrics)
    },
    
    # Calculate confidence score
    calculate_confidence_score = function(metrics) {
      if(metrics$total_trades < 5) return(0.1)
      
      # Simple confidence calculation
      win_rate_score <- metrics$win_rate
      return_score <- min(abs(metrics$avg_return) * 10, 1)  # Cap at 10% avg return
      
      confidence_score <- (win_rate_score * 0.7) + (return_score * 0.3)
      
      return(max(0, min(confidence_score, 1)))
    },
    
    # Run backtesting for a single stock
    backtest_stock = function(symbol) {
      cat("Backtesting:", symbol, "\n")
      
      # Filter data for the stock
      stock_data <- data %>% 
        filter(SYMBOL == symbol) %>%
        arrange(TIMESTAMP)
      
      if(nrow(stock_data) < 20) {
        cat("  Insufficient data for backtesting\n")
        return(NULL)
      }
      
      # Get trading signals for this stock
      stock_signals <- signals %>%
        filter(SYMBOL == symbol) %>%
        arrange(TIMESTAMP)
      
      if(nrow(stock_signals) == 0) {
        cat("  No trading signals found\n")
        return(NULL)
      }
      
      # Execute trades
      trades <- execute_trades(stock_data, stock_signals)
      
      if(nrow(trades) == 0) {
        cat("  No trades executed\n")
        return(NULL)
      }
      
      # Calculate metrics
      metrics <- calculate_performance_metrics(trades)
      confidence <- calculate_confidence_score(metrics)
      
      # Store results
      result <- data.frame(
        SYMBOL = symbol,
        TOTAL_TRADES = metrics$total_trades,
        PROFITABLE_TRADES = metrics$profitable_trades,
        WIN_RATE = metrics$win_rate,
        TOTAL_RETURN = metrics$total_return,
        AVG_RETURN = metrics$avg_return,
        CONFIDENCE_SCORE = confidence,
        stringsAsFactors = FALSE
      )
      
      return(list(
        trades = trades,
        metrics = metrics,
        confidence = confidence,
        summary = result
      ))
    },
    
    # Run backtesting for all stocks
    run_full_backtest = function() {
      cat("Starting backtesting analysis...\n")
      
      # Get unique symbols
      symbols <- unique(data$SYMBOL)
      cat("Found", length(symbols), "stocks to backtest\n")
      
      all_results <- data.frame()
      all_trades <- data.frame()
      
      for(symbol in symbols) {
        result <- backtest_stock(symbol)
        
        if(!is.null(result)) {
          all_results <- rbind(all_results, result$summary)
          all_trades <- rbind(all_trades, result$trades)
        }
      }
      
      results <<- all_results
      
      cat("Backtesting completed!\n")
      cat("Total stocks analyzed:", nrow(all_results), "\n")
      cat("Total trades executed:", nrow(all_trades), "\n")
      
      return(list(
        results = all_results,
        trades = all_trades
      ))
    },
    
    # Generate report
    generate_report = function() {
      if(nrow(results) == 0) {
        cat("No backtesting results available\n")
        return()
      }
      
      cat("\n============================================================\n")
      cat("BACKTESTING REPORT\n")
      cat("============================================================\n")
      
      # Overall performance
      cat("\nOVERALL PERFORMANCE:\n")
      cat("----------------------------------------\n")
      cat("Total Stocks Analyzed:", nrow(results), "\n")
      cat("Average Win Rate:", round(mean(results$WIN_RATE) * 100, 1), "%\n")
      cat("Average Confidence Score:", round(mean(results$CONFIDENCE_SCORE) * 100, 1), "%\n")
      cat("Average Total Return:", round(mean(results$TOTAL_RETURN) * 100, 1), "%\n")
      
      # Top performers
      cat("\nTOP PERFORMERS BY CONFIDENCE SCORE:\n")
      cat("--------------------------------------------------\n")
      top_performers <- results %>%
        arrange(desc(CONFIDENCE_SCORE)) %>%
        head(5)
      
      print(top_performers)
      
      # Recommendations
      cat("\nRECOMMENDATIONS:\n")
      cat("--------------------\n")
      avg_win_rate <- mean(results$WIN_RATE)
      avg_confidence <- mean(results$CONFIDENCE_SCORE)
      
      if(avg_win_rate < 0.5) {
        cat("• Low win rate suggests need for better entry/exit criteria\n")
      }
      if(avg_confidence < 0.6) {
        cat("• Low confidence scores indicate need for signal refinement\n")
      }
      if(avg_win_rate >= 0.5 && avg_confidence >= 0.6) {
        cat("• Trading engine performing well - consider optimization\n")
      }
    }
  )
)

# =============================================================================
# DEMONSTRATION
# =============================================================================

cat("Backtesting Engine Demonstration\n")
cat("==================================================\n")

# Create sample data
cat("Creating sample data...\n")
stock_data <- create_sample_stock_data()
cat("Created sample data for", length(unique(stock_data$SYMBOL)), "stocks\n")

# Create sample signals
cat("Creating sample trading signals...\n")
trading_signals <- create_sample_signals(stock_data)
cat("Generated", nrow(trading_signals), "trading signals\n")

# Initialize backtesting engine
cat("Initializing backtesting engine...\n")
engine <- SimpleBacktestingEngine$new(stock_data, trading_signals)

# Run backtesting
cat("Running backtesting analysis...\n")
results <- engine$run_full_backtest()

# Generate report
engine$generate_report()

# Show sample trades
if(!is.null(results) && nrow(results$trades) > 0) {
  cat("\nSAMPLE TRADES:\n")
  cat("------------------------------\n")
  print(head(results$trades, 5))
}

cat("\nBacktesting demonstration completed!\n")
cat("This demonstrates the core functionality of the backtesting engine.\n")
cat("In a real implementation, you would:\n")
cat("1. Use actual market data\n")
cat("2. Implement more sophisticated signal generation\n")
cat("3. Add risk management features\n")
cat("4. Include transaction costs and slippage\n")
cat("5. Add more performance metrics (Sharpe ratio, drawdown, etc.)\n")
