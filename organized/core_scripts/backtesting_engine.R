# =============================================================================
# BACKTESTING ENGINE FOR NSE TRADING SIGNALS
# =============================================================================
# This module evaluates the accuracy of trading signals and provides confidence scores
# to improve the overall trading engine accuracy

library(dplyr)
library(lubridate)
library(ggplot2)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Backtesting parameters
BACKTEST_DAYS <- 252  # One trading year
CONFIDENCE_THRESHOLD <- 0.7  # Minimum confidence score
MIN_TRADES <- 10  # Minimum trades for statistical significance

# Performance metrics weights for confidence scoring
WEIGHTS <- list(
  win_rate = 0.25,
  profit_factor = 0.20,
  max_drawdown = 0.15,
  sharpe_ratio = 0.15,
  avg_return = 0.15,
  signal_consistency = 0.10
)

# =============================================================================
# BACKTESTING ENGINE CLASS
# =============================================================================

BacktestingEngine <- setRefClass("BacktestingEngine",
  fields = list(
    data = "data.frame",
    signals = "data.frame",
    results = "data.frame",
    performance_metrics = "list",
    confidence_scores = "data.frame"
  ),
  
  methods = list(
    
    # Initialize the backtesting engine
    initialize = function(stock_data, trading_signals) {
      data <<- stock_data
      signals <<- trading_signals
      results <<- data.frame()
      performance_metrics <<- list()
      confidence_scores <<- data.frame()
    },
    
    # Run backtesting for a single stock
    backtest_stock = function(symbol, start_date = NULL, end_date = NULL) {
      cat("Backtesting:", symbol, "\n")
      
      # Filter data for the stock
      stock_data <- data %>% 
        filter(SYMBOL == symbol) %>%
        arrange(TIMESTAMP)
      
      if(nrow(stock_data) < BACKTEST_DAYS) {
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
      
      # Set date range
      if(is.null(start_date)) {
        start_date <- max(stock_data$TIMESTAMP) - days(BACKTEST_DAYS)
      }
      if(is.null(end_date)) {
        end_date <- max(stock_data$TIMESTAMP)
      }
      
      # Filter data for backtesting period
      backtest_data <- stock_data %>%
        filter(TIMESTAMP >= start_date, TIMESTAMP <= end_date)
      
      # Execute trades based on signals
      trades <- execute_trades(backtest_data, stock_signals)
      
      if(nrow(trades) == 0) {
        cat("  No trades executed\n")
        return(NULL)
      }
      
      # Calculate performance metrics
      metrics <- calculate_performance_metrics(trades, backtest_data)
      
      # Calculate confidence score
      confidence <- calculate_confidence_score(metrics, trades)
      
      # Store results
      result <- data.frame(
        SYMBOL = symbol,
        START_DATE = start_date,
        END_DATE = end_date,
        TOTAL_TRADES = nrow(trades),
        WINNING_TRADES = sum(trades$profit > 0, na.rm = TRUE),
        LOSING_TRADES = sum(trades$profit < 0, na.rm = TRUE),
        WIN_RATE = metrics$win_rate,
        TOTAL_RETURN = metrics$total_return,
        ANNUALIZED_RETURN = metrics$annualized_return,
        MAX_DRAWDOWN = metrics$max_drawdown,
        SHARPE_RATIO = metrics$sharpe_ratio,
        PROFIT_FACTOR = metrics$profit_factor,
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
    
    # Execute trades based on signals
    execute_trades = function(backtest_data, signals) {
      trades <- data.frame()
      position <- NULL
      entry_price <- 0
      entry_date <- NULL
      
      for(i in 1:nrow(backtest_data)) {
        current_data <- backtest_data[i, ]
        current_signal <- signals %>%
          filter(TIMESTAMP <= current_data$TIMESTAMP) %>%
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
    calculate_performance_metrics = function(trades, backtest_data) {
      if(nrow(trades) == 0) {
        return(list(
          win_rate = 0,
          total_return = 0,
          annualized_return = 0,
          max_drawdown = 0,
          sharpe_ratio = 0,
          profit_factor = 0
        ))
      }
      
      # Basic metrics
      winning_trades <- trades[trades$profit > 0, ]
      losing_trades <- trades[trades$profit < 0, ]
      
      win_rate <- nrow(winning_trades) / nrow(trades)
      total_return <- sum(trades$profit, na.rm = TRUE)
      
      # Annualized return
      days_held <- sum(trades$holding_days, na.rm = TRUE)
      annualized_return <- ifelse(days_held > 0, 
                                 (1 + total_return)^(365/days_held) - 1, 
                                 0)
      
      # Maximum drawdown
      cumulative_returns <- cumsum(trades$profit)
      running_max <- cummax(cumulative_returns)
      drawdowns <- cumulative_returns - running_max
      max_drawdown <- min(drawdowns, na.rm = TRUE)
      
      # Sharpe ratio (simplified)
      returns <- trades$profit
      sharpe_ratio <- ifelse(length(returns) > 1 && sd(returns) > 0,
                            mean(returns) / sd(returns) * sqrt(252),
                            0)
      
      # Profit factor
      gross_profit <- sum(winning_trades$profit, na.rm = TRUE)
      gross_loss <- abs(sum(losing_trades$profit, na.rm = TRUE))
      profit_factor <- ifelse(gross_loss > 0, gross_profit / gross_loss, 0)
      
      return(list(
        win_rate = win_rate,
        total_return = total_return,
        annualized_return = annualized_return,
        max_drawdown = max_drawdown,
        sharpe_ratio = sharpe_ratio,
        profit_factor = profit_factor
      ))
    },
    
    # Calculate confidence score based on performance
    calculate_confidence_score = function(metrics, trades) {
      if(nrow(trades) < MIN_TRADES) {
        return(0.1)  # Low confidence for insufficient data
      }
      
      # Normalize metrics to 0-1 scale
      win_rate_score <- metrics$win_rate
      
      profit_factor_score <- min(metrics$profit_factor / 2, 1)  # Cap at 2.0
      
      drawdown_score <- max(0, 1 + metrics$max_drawdown)  # Convert to positive scale
      
      sharpe_score <- max(0, min(metrics$sharpe_ratio / 2, 1))  # Cap at 2.0
      
      avg_return_score <- max(0, min(metrics$annualized_return / 0.5, 1))  # Cap at 50%
      
      # Signal consistency (how often signals are followed)
      signal_consistency <- calculate_signal_consistency(trades)
      
      # Weighted confidence score
      confidence_score <- 
        WEIGHTS$win_rate * win_rate_score +
        WEIGHTS$profit_factor * profit_factor_score +
        WEIGHTS$max_drawdown * drawdown_score +
        WEIGHTS$sharpe_ratio * sharpe_score +
        WEIGHTS$avg_return * avg_return_score +
        WEIGHTS$signal_consistency * signal_consistency
      
      return(max(0, min(confidence_score, 1)))  # Ensure 0-1 range
    },
    
    # Calculate signal consistency
    calculate_signal_consistency = function(trades) {
      if(nrow(trades) < 2) return(0.5)
      
      # Calculate how consistent the signals are
      # Higher consistency = better confidence
      holding_periods <- trades$holding_days
      consistency <- 1 - (sd(holding_periods) / mean(holding_periods))
      
      return(max(0, min(consistency, 1)))
    },
    
    # Run backtesting for all stocks
    run_full_backtest = function() {
      cat("Starting full backtesting analysis...\n")
      
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
      
      # Calculate overall performance metrics
      overall_metrics <- calculate_overall_metrics(all_results, all_trades)
      performance_metrics <<- overall_metrics
      
      # Generate confidence scores
      confidence_scores <<- generate_confidence_analysis(all_results)
      
      cat("Backtesting completed!\n")
      cat("Total stocks analyzed:", nrow(all_results), "\n")
      cat("Total trades executed:", nrow(all_trades), "\n")
      
      return(list(
        results = all_results,
        trades = all_trades,
        metrics = overall_metrics,
        confidence = confidence_scores
      ))
    },
    
    # Calculate overall performance metrics
    calculate_overall_metrics = function(results, trades) {
      if(nrow(results) == 0) return(list())
      
      overall_metrics <- list(
        total_stocks = nrow(results),
        avg_win_rate = mean(results$WIN_RATE, na.rm = TRUE),
        avg_confidence = mean(results$CONFIDENCE_SCORE, na.rm = TRUE),
        avg_return = mean(results$ANNUALIZED_RETURN, na.rm = TRUE),
        avg_sharpe = mean(results$SHARPE_RATIO, na.rm = TRUE),
        total_trades = nrow(trades),
        profitable_stocks = sum(results$TOTAL_RETURN > 0, na.rm = TRUE),
        high_confidence_stocks = sum(results$CONFIDENCE_SCORE >= CONFIDENCE_THRESHOLD, na.rm = TRUE)
      )
      
      return(overall_metrics)
    },
    
    # Generate confidence analysis
    generate_confidence_analysis = function(results) {
      if(nrow(results) == 0) return(data.frame())
      
      # Group by confidence levels
      confidence_analysis <- results %>%
        mutate(
          CONFIDENCE_LEVEL = case_when(
            CONFIDENCE_SCORE >= 0.8 ~ "Very High",
            CONFIDENCE_SCORE >= 0.6 ~ "High", 
            CONFIDENCE_SCORE >= 0.4 ~ "Medium",
            CONFIDENCE_SCORE >= 0.2 ~ "Low",
            TRUE ~ "Very Low"
          )
        ) %>%
        group_by(CONFIDENCE_LEVEL) %>%
        summarise(
          COUNT = n(),
          AVG_WIN_RATE = mean(WIN_RATE, na.rm = TRUE),
          AVG_RETURN = mean(ANNUALIZED_RETURN, na.rm = TRUE),
          AVG_SHARPE = mean(SHARPE_RATIO, na.rm = TRUE),
          .groups = 'drop'
        ) %>%
        arrange(desc(AVG_RETURN))
      
      return(confidence_analysis)
    },
    
    # Generate backtesting report
    generate_report = function() {
      if(nrow(results) == 0) {
        cat("No backtesting results available\n")
        return()
      }
      
      cat("\n" , "=", 80, "\n")
      cat("BACKTESTING REPORT\n")
      cat("=", 80, "\n")
      
      # Overall performance
      cat("\nOVERALL PERFORMANCE:\n")
      cat("-" * 40, "\n")
      cat("Total Stocks Analyzed:", performance_metrics$total_stocks, "\n")
      cat("Total Trades Executed:", performance_metrics$total_trades, "\n")
      cat("Average Win Rate:", round(performance_metrics$avg_win_rate * 100, 1), "%\n")
      cat("Average Confidence Score:", round(performance_metrics$avg_confidence * 100, 1), "%\n")
      cat("Average Annual Return:", round(performance_metrics$avg_return * 100, 1), "%\n")
      cat("Profitable Stocks:", performance_metrics$profitable_stocks, "/", performance_metrics$total_stocks, "\n")
      cat("High Confidence Stocks:", performance_metrics$high_confidence_stocks, "/", performance_metrics$total_stocks, "\n")
      
      # Top performers
      cat("\nTOP 10 PERFORMERS BY CONFIDENCE SCORE:\n")
      cat("-" * 50, "\n")
      top_performers <- results %>%
        arrange(desc(CONFIDENCE_SCORE)) %>%
        head(10) %>%
        select(SYMBOL, CONFIDENCE_SCORE, WIN_RATE, ANNUALIZED_RETURN, TOTAL_TRADES)
      
      print(top_performers)
      
      # Confidence analysis
      cat("\nCONFIDENCE LEVEL ANALYSIS:\n")
      cat("-" * 40, "\n")
      print(confidence_scores)
      
      # Recommendations
      cat("\nRECOMMENDATIONS FOR IMPROVEMENT:\n")
      cat("-" * 40, "\n")
      generate_improvement_recommendations()
    },
    
    # Generate improvement recommendations
    generate_improvement_recommendations = function() {
      recommendations <- c()
      
      if(performance_metrics$avg_win_rate < 0.5) {
        recommendations <- c(recommendations, 
          "• Low win rate suggests need for better entry/exit criteria")
      }
      
      if(performance_metrics$avg_confidence < 0.6) {
        recommendations <- c(recommendations,
          "• Low confidence scores indicate need for signal refinement")
      }
      
      if(performance_metrics$avg_return < 0.1) {
        recommendations <- c(recommendations,
          "• Low returns suggest need for better risk management")
      }
      
      if(length(recommendations) == 0) {
        recommendations <- c("• Trading engine performing well - consider optimization")
      }
      
      cat(paste(recommendations, collapse = "\n"), "\n")
    },
    
    # Save results to files
    save_results = function(output_dir = "output/backtesting") {
      if(!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
      }
      
      timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
      
      # Save detailed results
      write.csv(results, file.path(output_dir, paste0("backtest_results_", timestamp, ".csv")), row.names = FALSE)
      
      # Save confidence analysis
      write.csv(confidence_scores, file.path(output_dir, paste0("confidence_analysis_", timestamp, ".csv")), row.names = FALSE)
      
      # Save performance metrics
      saveRDS(performance_metrics, file.path(output_dir, paste0("performance_metrics_", timestamp, ".rds")))
      
      cat("Results saved to:", output_dir, "\n")
    }
  )
)

# =============================================================================
# ACCURACY IMPROVEMENT FUNCTIONS
# =============================================================================

# Function to analyze signal accuracy patterns
analyze_signal_patterns <- function(backtest_results) {
  cat("Analyzing signal accuracy patterns...\n")
  
  # Group by signal type and analyze performance
  signal_analysis <- backtest_results %>%
    group_by(SIGNAL_TYPE = case_when(
      WIN_RATE >= 0.7 ~ "High Accuracy",
      WIN_RATE >= 0.5 ~ "Medium Accuracy", 
      TRUE ~ "Low Accuracy"
    )) %>%
    summarise(
      COUNT = n(),
      AVG_CONFIDENCE = mean(CONFIDENCE_SCORE, na.rm = TRUE),
      AVG_RETURN = mean(ANNUALIZED_RETURN, na.rm = TRUE),
      .groups = 'drop'
    )
  
  return(signal_analysis)
}

# Function to optimize signal parameters
optimize_signal_parameters <- function(data, signals, param_ranges) {
  cat("Optimizing signal parameters...\n")
  
  best_params <- list()
  best_score <- 0
  
  # Grid search for optimal parameters
  for(rsi_threshold in param_ranges$rsi) {
    for(momentum_threshold in param_ranges$momentum) {
      for(volume_threshold in param_ranges$volume) {
        
        # Apply parameters to signals
        optimized_signals <- apply_signal_parameters(signals, 
                                                   rsi_threshold, 
                                                   momentum_threshold, 
                                                   volume_threshold)
        
        # Run quick backtest
        engine <- BacktestingEngine$new(data, optimized_signals)
        results <- engine$run_full_backtest()
        
        # Calculate optimization score
        score <- mean(results$results$CONFIDENCE_SCORE, na.rm = TRUE)
        
        if(score > best_score) {
          best_score <- score
          best_params <- list(
            rsi_threshold = rsi_threshold,
            momentum_threshold = momentum_threshold,
            volume_threshold = volume_threshold,
            score = score
          )
        }
      }
    }
  }
  
  return(best_params)
}

# Function to apply optimized parameters
apply_signal_parameters <- function(signals, rsi_thresh, momentum_thresh, volume_thresh) {
  # Apply parameter-based filtering to signals
  optimized_signals <- signals %>%
    filter(
      RSI >= rsi_thresh,
      abs(MOMENTUM_50D) >= momentum_thresh,
      VOLUME_RATIO >= volume_thresh
    )
  
  return(optimized_signals)
}

# =============================================================================
# MAIN EXECUTION FUNCTION
# =============================================================================

run_backtesting_analysis <- function(stock_data, trading_signals, 
                                   output_dir = "output/backtesting") {
  
  cat("Starting comprehensive backtesting analysis...\n")
  cat("============================================================\n")
  
  # Initialize backtesting engine
  engine <- BacktestingEngine$new(stock_data, trading_signals)
  
  # Run full backtesting
  results <- engine$run_full_backtest()
  
  # Generate report
  engine$generate_report()
  
  # Analyze signal patterns
  signal_patterns <- analyze_signal_patterns(results$results)
  cat("\nSIGNAL PATTERN ANALYSIS:\n")
  cat("-" * 30, "\n")
  print(signal_patterns)
  
  # Save results
  engine$save_results(output_dir)
  
  # Return results for further analysis
  return(list(
    engine = engine,
    results = results,
    signal_patterns = signal_patterns
  ))
}

# =============================================================================
# USAGE EXAMPLE
# =============================================================================

# Example usage:
# backtest_results <- run_backtesting_analysis(stock_data, trading_signals)
# 
# # Access results
# engine <- backtest_results$engine
# results <- backtest_results$results
# 
# # Get top performers
# top_stocks <- results$results %>%
#   filter(CONFIDENCE_SCORE >= 0.7) %>%
#   arrange(desc(ANNUALIZED_RETURN))
# 
# # Analyze specific stock
# stock_analysis <- engine$backtest_stock("RELIANCE")

cat("Backtesting engine loaded successfully!\n")
cat("Use run_backtesting_analysis() to start backtesting\n")
