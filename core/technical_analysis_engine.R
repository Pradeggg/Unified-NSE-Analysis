# ================================================================================
# UNIFIED TECHNICAL ANALYSIS ENGINE
# ================================================================================
# Purpose: Centralized technical analysis calculations for both stocks and indices
# ================================================================================

#' Calculate all technical indicators for a given price dataset
#' @param price_data Data frame with OHLC data and volume
#' @param symbol_name Character symbol name for reference
#' @param is_index Boolean indicating if this is index data
#' @param config Analysis configuration list
#' @return List of calculated technical indicators
calculate_technical_indicators <- function(price_data, symbol_name, is_index = FALSE, config = ANALYSIS_CONFIG) {
  
  tryCatch({
    # Initialize results list
    result <- list()
    
    # Validate input data
    required_cols <- c("CLOSE", "OPEN", "HIGH", "LOW")
    if(!all(required_cols %in% names(price_data))) {
      warning(paste("Missing required columns for", symbol_name))
      return(NULL)
    }
    
    if(nrow(price_data) < config$min_historical_days) {
      warning(paste("Insufficient data for", symbol_name, "- need at least", config$min_historical_days, "days"))
      return(NULL)
    }
    
    # Sort data by date to ensure proper calculation
    if("TIMESTAMP" %in% names(price_data)) {
      price_data <- price_data[order(price_data$TIMESTAMP), ]
    }
    
    # ========================================
    # 1. EXPONENTIAL MOVING AVERAGES (EMA)
    # ========================================
    for(period in config$ema_periods) {
      ema_col <- paste0("EMA", period, "_FLG")
      
      ema_values <- EMA(ts(price_data$CLOSE), n = period)
      current_close <- tail(price_data$CLOSE, 1)
      current_ema <- tail(ema_values, 1)
      
      result[[ema_col]] <- ifelse(
        !is.na(current_ema) && current_close >= as.numeric(current_ema), 1, 0
      )
    }
    
    # ========================================
    # 2. SIMPLE MOVING AVERAGE (SMA)
    # ========================================
    sma_20 <- SMA(ts(price_data$CLOSE), n = 10) # Note: using n=10 to match legacy
    result$SMA20_FLG <- ifelse(
      tail(price_data$CLOSE, 1) >= as.numeric(tail(sma_20, 1)), 1, 0
    )
    
    # ========================================
    # 3. VOLUME EXPONENTIAL MOVING AVERAGES
    # ========================================
    if("TOTTRDQTY" %in% names(price_data) && (!is_index || sum(price_data$TOTTRDQTY, na.rm = TRUE) > 0)) {
      
      for(period in config$vema_periods) {
        vema_col <- paste0("VEMA", period, "_FLG")
        
        vema_values <- EMA(price_data$TOTTRDQTY, n = period)
        vema_values[is.na(vema_values)] <- 0
        
        current_volume <- tail(price_data$TOTTRDQTY, 1)
        current_vema <- tail(vema_values, 1)
        
        result[[vema_col]] <- ifelse(
          !is.na(current_vema) && current_volume >= as.numeric(current_vema), 1, 0
        )
      }
    } else {
      # Set default values for indices without meaningful volume
      for(period in config$vema_periods) {
        vema_col <- paste0("VEMA", period, "_FLG")
        result[[vema_col]] <- 0
      }
    }
    
    # ========================================
    # 4. RELATIVE STRENGTH INDEX (RSI)
    # ========================================
    rsi_values <- RSI(price_data$CLOSE, n = config$rsi_period)
    result$RSI <- tail(rsi_values, 1)
    result$RSIIND <- ifelse(result$RSI > 50, 1, 0)
    
    # ========================================
    # 5. MACD INDICATOR
    # ========================================
    macd_data <- as.data.frame(MACD(
      price_data$CLOSE, 
      nFast = config$macd_params$nFast, 
      nSlow = config$macd_params$nSlow, 
      nSig = config$macd_params$nSig, 
      maType = SMA, 
      percent = FALSE
    ))
    
    if(nrow(macd_data) > 0) {
      signal <- Lag(ifelse(macd_data$macd < macd_data$signal, -1, 1))
      result$MACDIND <- tail(signal, 1)
      result$macd <- tail(macd_data$macd, 1)
      result$signal <- tail(macd_data$signal, 1)
      result$MACDSIG <- result$MACDIND
    }
    
    # ========================================
    # 6. AROON INDICATOR
    # ========================================
    if(nrow(price_data) >= config$aroon_period) {
      aroon_data <- as.data.frame(aroon(ts(price_data[, c('HIGH', 'LOW')]), n = config$aroon_period))
      
      if(nrow(aroon_data) > 0) {
        aroon_signal <- ifelse(
          (aroon_data$aroonDn >= 50 & aroon_data$aroonUp < 30), 0,
          ifelse(aroon_data$aroonUp >= 70 | aroon_data$aroonDn < 30, 1, -1)
        )
        
        result$arnsig <- tail(aroon_signal, 1)
        result$aroonUp <- tail(aroon_data$aroonUp, 1)
        result$aroonDn <- tail(aroon_data$aroonDn, 1)
        result$oscillator <- result$aroonUp - result$aroonDn
      }
    }
    
    # ========================================
    # 7. BOLLINGER BANDS
    # ========================================
    bb_data <- as.data.frame(BBands(
      price_data$CLOSE, 
      sd = config$bollinger_params$sd, 
      n = config$bollinger_params$n, 
      maType = EMA
    ))
    
    if(nrow(bb_data) > 0) {
      bb_signal <- ifelse(
        (price_data$CLOSE > bb_data$mavg | price_data$CLOSE > bb_data$up) | price_data$HIGH >= bb_data$up, 1,
        ifelse(price_data$CLOSE > bb_data$mavg, 0, -1)
      )
      
      result$BBSIG <- ifelse(
        sum(tail(bb_signal, 4)) > 0, 1,
        ifelse(sum(tail(bb_signal, 5)) == 0, 0, -1)
      )
    }
    
    # ========================================
    # 8. TREND CALCULATIONS
    # ========================================
    if(nrow(price_data) >= 16) {
      result$trend.close <- trend_close(tail(price_data, 16))
      result$trend.high <- trend_high(tail(price_data, 16))
      result$trend.low <- trend_low(tail(price_data, 16))
    }
    
    # ========================================
    # 9. GAIN CALCULATIONS
    # ========================================
    for(period in config$gain_periods) {
      gain_col <- paste0("gain", period)
      
      if(nrow(price_data) >= period) {
        current_price <- tail(price_data$CLOSE, 1)
        past_price <- head(tail(price_data$CLOSE, period), 1)
        
        if(!is.na(past_price) && past_price != 0) {
          result[[gain_col]] <- ((current_price - past_price) * 100 / past_price) / period
        } else {
          result[[gain_col]] <- 0
        }
      } else {
        result[[gain_col]] <- 0
      }
    }
    
    # ========================================
    # 10. LOG RETURNS
    # ========================================
    for(period in config$logret_periods) {
      logret_col <- paste0("logret", period)
      
      if(nrow(price_data) >= period) {
        result[[logret_col]] <- logreturns(price_data$CLOSE, period) * 100
      } else {
        result[[logret_col]] <- 0
      }
    }
    
    # ========================================
    # 11. VOLATILITY
    # ========================================
    if(nrow(price_data) >= 200) {
      result$volatility <- volatility(tail(price_data$CLOSE, 200))
    } else {
      result$volatility <- 0
    }
    
    # ========================================
    # 12. COMPOSITE INDICATORS
    # ========================================
    # Price Moving Average (PMA) - sum of key EMA flags
    result$PMA <- result$EMA20_FLG + result$EMA30_FLG + result$EMA40_FLG + 
                  result$EMA50_FLG + result$EMA100_FLG
    
    # Volume Moving Average (VMA) - sum of key VEMA flags
    result$VMA <- result$VEMA20_FLG + result$VEMA30_FLG + 
                  result$VEMA50_FLG + result$VEMA100_FLG
    
    # ========================================
    # 13. AGING CALCULATIONS (Placeholder)
    # ========================================
    result$HIGH_AGING <- 0
    result$LOW_AGING <- 0
    
    return(result)
    
  }, error = function(e) {
    warning(paste("Error calculating technical indicators for", symbol_name, ":", e$message))
    return(NULL)
  })
}

#' Batch process technical analysis for multiple symbols
#' @param symbol_data Data frame with symbol information
#' @param historical_data Complete historical data
#' @param analysis_type Type of analysis ("index" or "stock")
#' @param config Analysis configuration
#' @return Data frame with technical indicators added
batch_technical_analysis <- function(symbol_data, historical_data, analysis_type = "index", config = ANALYSIS_CONFIG) {
  
  cat("Starting batch technical analysis for", nrow(symbol_data), "symbols...\n")
  
  results_list <- list()
  
  for(i in 1:nrow(symbol_data)) {
    symbol <- symbol_data$SYMBOL[i]
    
    # Progress indicator
    if(i %% 10 == 0) {
      cat("Processing symbol", i, "of", nrow(symbol_data), ":", symbol, "\n")
    }
    
    # Extract historical data for this symbol
    symbol_history <- historical_data[historical_data$SYMBOL == symbol, ]
    
    if(nrow(symbol_history) < config$min_historical_days) {
      next
    }
    
    # Calculate technical indicators
    indicators <- calculate_technical_indicators(
      symbol_history, 
      symbol, 
      is_index = (analysis_type == "index"),
      config = config
    )
    
    if(!is.null(indicators)) {
      # Combine base data with indicators
      result_row <- cbind(symbol_data[i, ], as.data.frame(indicators))
      results_list[[length(results_list) + 1]] <- result_row
    }
  }
  
  if(length(results_list) > 0) {
    final_results <- do.call(rbind, results_list)
    cat("Completed technical analysis for", nrow(final_results), "symbols\n")
    return(final_results)
  } else {
    warning("No symbols processed successfully")
    return(data.frame())
  }
}

#' Validate technical analysis results
#' @param results Data frame with technical analysis results
#' @return Boolean indicating if results are valid
validate_technical_results <- function(results) {
  
  if(nrow(results) == 0) {
    warning("No results to validate")
    return(FALSE)
  }
  
  # Check for essential columns
  essential_cols <- c("RSI", "MACDIND", "PMA", "VMA", "volatility")
  missing_cols <- essential_cols[!essential_cols %in% names(results)]
  
  if(length(missing_cols) > 0) {
    warning("Missing essential columns:", paste(missing_cols, collapse = ", "))
    return(FALSE)
  }
  
  # Check for reasonable value ranges
  if(any(results$RSI < 0 | results$RSI > 100, na.rm = TRUE)) {
    warning("RSI values outside expected range [0, 100]")
  }
  
  cat("Technical analysis validation passed for", nrow(results), "records\n")
  return(TRUE)
}
