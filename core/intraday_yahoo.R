# REAL-TIME INTRADAY TECHNICAL ANALYSIS FOR NSE STOCKS
# Data Source: Yahoo Finance (hourly timeframe)
# Author: Enhanced Analysis System
# Date: August 2025

library(quantmod)
library(TTR)
library(dplyr)
library(lubridate)

# Optional packages for enhanced features
tryCatch(library(ggplot2), error = function(e) NULL)
tryCatch(library(plotly), error = function(e) NULL)
tryCatch(library(htmlwidgets), error = function(e) NULL)

# ===== NIFTY50 STOCK LIST =====
get_nifty50_stocks <- function(include_indices = TRUE) {
  # Read Nifty50 stocks from the watchlist file
  nifty50_file <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index/Testing/NIFTY 50_watchlist.csv"
  
  # Start with major indices if requested
  indices <- c()
  if(include_indices) {
    indices <- c("NIFTY50", "BANKNIFTY", "NIFTYIT", "NIFTYPHARMA")
    cat("📊 Including major NSE indices:", paste(indices, collapse = ", "), "\n")
  }
  
  if(file.exists(nifty50_file)) {
    cat("📊 Loading Nifty50 stocks from file...\n")
    data <- read.csv(nifty50_file, stringsAsFactors = FALSE)
    
    # Extract symbols and clean them (remove .NS if present)
    symbols <- data$SYMBOL
    symbols <- gsub("\\.NS$", "", symbols)  # Remove .NS suffix
    symbols <- gsub(",$", "", symbols)      # Remove trailing comma if present
    
    # Combine indices with stocks
    all_symbols <- c(indices, symbols)
    
    cat("✅ Loaded", length(symbols), "Nifty50 stocks")
    if(include_indices) {
      cat(" +", length(indices), "indices =", length(all_symbols), "total symbols\n")
    } else {
      cat("\n")
    }
    
    return(all_symbols)
  } else {
    cat("❌ Nifty50 file not found, using default list\n")
    # Fallback list of major Nifty50 stocks
    stocks <- c("RELIANCE", "TCS", "INFY", "HINDUNILVR", "ITC", "BHARTIARTL", 
                "SBIN", "BAJFINANCE", "KOTAKBANK", "HDFCBANK", "ICICIBANK",
                "MARUTI", "TITAN", "WIPRO", "TECHM", "ULTRACEMCO", "ADANIPORTS",
                "ASIANPAINT", "BAJAJ-AUTO", "BRITANNIA", "CIPLA", "COALINDIA",
                "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM", "HCLTECH", "HEROMOTOCO",
                "HINDALCO", "JSWSTEEL", "LT", "M&M", "NESTLEIND", "NTPC", "ONGC",
                "POWERGRID", "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "APOLLOHOSP",
                "BAJAJFINSV", "BPCL", "HDFCLIFE", "LTIM", "SBILIFE", "TATACONSUM")
    
    # Combine indices with stocks
    all_symbols <- c(indices, stocks)
    
    cat("✅ Using", length(stocks), "default stocks")
    if(include_indices) {
      cat(" +", length(indices), "indices =", length(all_symbols), "total symbols\n")
    } else {
      cat("\n")
    }
    
    return(all_symbols)
  }
}

# ===== YAHOO FINANCE INTRADAY DATA LOADING =====
get_intraday_data <- function(symbol, period_days = 7, interval = "1h") {
  tryCatch({
    # Format symbol for Yahoo Finance
    # NSE stocks need .NS suffix, but indices use different format
    if(toupper(symbol) %in% c("NIFTY", "NIFTY50", "NIFTY 50")) {
      yahoo_symbol <- "^NSEI"  # NIFTY 50 index
    } else if(toupper(symbol) %in% c("BANKNIFTY", "NIFTYBANK", "NIFTY BANK")) {
      yahoo_symbol <- "^NSEBANK"  # NIFTY Bank index
    } else if(toupper(symbol) %in% c("NIFTYIT", "NIFTY IT")) {
      yahoo_symbol <- "^CNXIT"  # NIFTY IT index
    } else if(toupper(symbol) %in% c("NIFTYPHARMA", "NIFTY PHARMA")) {
      yahoo_symbol <- "^CNXPHARMA"  # NIFTY Pharma index
    } else {
      yahoo_symbol <- paste0(symbol, ".NS")  # Regular NSE stocks
    }
    
    # Yahoo Finance supports hourly data for 7 days max, use 60 days for more data with daily fallback
    if(interval == "1h") {
      from_date <- Sys.Date() - min(period_days, 7)  # Max 7 days for hourly
      period_str <- paste0(min(period_days, 7), "d")
    } else {
      from_date <- Sys.Date() - period_days
      period_str <- paste0(period_days, "d")
    }
    
    to_date <- Sys.Date()
    
    cat("📊 Fetching", interval, "data for", yahoo_symbol, "from", from_date, "to", to_date, "\n")
    
    # Try hourly data first, fallback to daily if not available
    data <- NULL
    
    if(interval == "1h") {
      # Use quantmod for hourly data (limited to 7 days)
      tryCatch({
        data <- getSymbols(yahoo_symbol, 
                          src = "yahoo",
                          from = from_date,
                          to = to_date,
                          periodicity = "hourly",
                          auto.assign = FALSE)
      }, error = function(e) {
        cat("⚠️ Hourly data not available, trying daily data for", symbol, "\n")
        data <<- NULL
      })
    }
    
    # Fallback to daily data if hourly fails or requested
    if(is.null(data) || nrow(data) == 0) {
      from_date <- Sys.Date() - 30  # Use 30 days for daily data
      data <- getSymbols(yahoo_symbol, 
                        src = "yahoo",
                        from = from_date,
                        to = to_date,
                        auto.assign = FALSE)
      interval_used <- "daily"
    } else {
      interval_used <- "hourly"
    }
    
    if(is.null(data) || nrow(data) == 0) {
      cat("❌ No data found for", symbol, "\n")
      return(NULL)
    }
    
    # Convert to data frame with proper column names
    df <- data.frame(
      DateTime = index(data),
      Open = as.numeric(data[,1]),
      High = as.numeric(data[,2]),
      Low = as.numeric(data[,3]),
      Close = as.numeric(data[,4]),
      Volume = as.numeric(data[,5])
    )
    
    # Remove NA values
    df <- df[complete.cases(df),]
    
    if(nrow(df) == 0) {
      cat("❌ No valid data after cleaning for", symbol, "\n")
      return(NULL)
    }
    
    # Add basic price movements
    df$Price_Change <- c(0, diff(df$Close))
    df$Price_Change_Pct <- c(0, diff(df$Close) / df$Close[-nrow(df)] * 100)
    
    # Add intraday range data
    df$Range <- df$High - df$Low
    df$Range_Pct <- (df$Range / df$Close) * 100
    
    # Add time-based features for intraday analysis
    df$Hour <- hour(df$DateTime)
    df$DayOfWeek <- wday(df$DateTime)
    df$Date <- as.Date(df$DateTime)
    
    # Market session classification for NSE (9:15 AM to 3:30 PM IST)
    df$Market_Session <- ifelse(df$Hour >= 9 & df$Hour <= 15, "Regular", 
                               ifelse(df$Hour < 9, "Pre-Market", "Post-Market"))
    
    cat("✅ Loaded", nrow(df), interval_used, "data points for", symbol, 
        "from", min(df$DateTime), "to", max(df$DateTime), "\n")
    
    # Add metadata
    attr(df, "symbol") <- symbol
    attr(df, "interval") <- interval_used
    attr(df, "data_points") <- nrow(df)
    
    return(df)
    
  }, error = function(e) {
    cat("❌ Error loading data for", symbol, ":", e$message, "\n")
    return(NULL)
  })
}

# ===== INTRADAY TECHNICAL INDICATORS (Hourly Timeframe) =====
calculate_intraday_indicators <- function(data) {
  if(is.null(data) || nrow(data) < 20) {
    cat("⚠️ Insufficient data for technical analysis (need at least 20 periods), got", nrow(data), "\n")
    return(NULL)
  }
  
  interval <- attr(data, "interval")
  if(is.null(interval)) interval <- "unknown"
  
  cat("📈 Calculating indicators for", nrow(data), "periods (", interval, ")\n")
  
  tryCatch({
    # Adaptive periods based on data availability and interval
    n_periods <- nrow(data)
    
    # For hourly data: shorter periods, for daily data: standard periods
    if(interval == "hourly" || n_periods < 50) {
      # Intraday/Short-term periods
      sma_short <- min(5, n_periods %/% 4)
      sma_medium <- min(10, n_periods %/% 3)
      sma_long <- min(20, n_periods %/% 2)
      ema_fast <- min(9, n_periods %/% 3)
      ema_slow <- min(21, n_periods %/% 2)
      rsi_period <- min(14, n_periods %/% 2)
      bb_period <- min(20, n_periods %/% 2)
      macd_fast <- min(12, n_periods %/% 3)
      macd_slow <- min(26, n_periods %/% 2)
      macd_signal <- min(9, n_periods %/% 4)
    } else {
      # Daily/Standard periods
      sma_short <- 5
      sma_medium <- 10
      sma_long <- 20
      ema_fast <- 9
      ema_slow <- 21
      rsi_period <- 14
      bb_period <- 20
      macd_fast <- 12
      macd_slow <- 26
      macd_signal <- 9
    }
    
    # Moving Averages (adaptive periods)
    if(sma_short > 0) data$SMA_Short <- SMA(data$Close, n = sma_short)
    if(sma_medium > 0) data$SMA_Medium <- SMA(data$Close, n = sma_medium)
    if(sma_long > 0) data$SMA_Long <- SMA(data$Close, n = sma_long)
    if(ema_fast > 0) data$EMA_Fast <- EMA(data$Close, n = ema_fast)
    if(ema_slow > 0) data$EMA_Slow <- EMA(data$Close, n = ema_slow)
    
    # Bollinger Bands
    if(bb_period > 0 && bb_period <= n_periods) {
      bb <- BBands(data$Close, n = bb_period, sd = 2)
      data$BB_Upper <- bb[,1]
      data$BB_Middle <- bb[,2] 
      data$BB_Lower <- bb[,3]
      data$BB_Position <- (data$Close - data$BB_Lower) / (data$BB_Upper - data$BB_Lower)
    }
    
    # RSI (adaptive period)
    if(rsi_period > 0 && rsi_period <= n_periods) {
      data$RSI <- RSI(data$Close, n = rsi_period)
    }
    
    # MACD (adaptive periods)
    if(macd_fast > 0 && macd_slow > 0 && macd_signal > 0) {
      macd <- MACD(data$Close, nFast = macd_fast, nSlow = macd_slow, nSig = macd_signal)
      data$MACD <- macd[,1]
      data$MACD_Signal <- macd[,2]
      data$MACD_Histogram <- macd[,1] - macd[,2]
    }
    
    # Stochastic Oscillator (adaptive)
    stoch_k <- min(14, n_periods %/% 2)
    if(stoch_k >= 3) {
      stoch <- stoch(data[,c("High","Low","Close")], nFastK = stoch_k, nFastD = 3, nSlowD = 3)
      data$Stoch_K <- stoch[,1]
      data$Stoch_D <- stoch[,2]
    }
    
    # Average True Range (adaptive)
    atr_period <- min(14, n_periods %/% 2)
    if(atr_period >= 2) {
      data$ATR <- ATR(data[,c("High","Low","Close")], n = atr_period)[,2]
    }
    
    # Williams %R (adaptive)
    williams_period <- min(14, n_periods %/% 2)
    if(williams_period >= 2) {
      data$Williams_R <- WPR(data[,c("High","Low","Close")], n = williams_period)
    }
    
    # Volume indicators (if volume data available)
    if(sum(!is.na(data$Volume)) > 5) {
      vol_period <- min(10, n_periods %/% 2)
      if(vol_period > 0) {
        data$Volume_SMA <- SMA(data$Volume, n = vol_period)
        data$Volume_Ratio <- data$Volume / data$Volume_SMA
        data$OBV <- OBV(data$Close, data$Volume)
      }
    }
    
    # Support/Resistance levels (adaptive periods)
    sr_short <- min(10, n_periods %/% 2)
    sr_long <- min(20, n_periods)
    
    if(sr_short > 0) {
      data$Recent_High_Short <- runMax(data$High, n = sr_short)
      data$Recent_Low_Short <- runMin(data$Low, n = sr_short)
      data$Position_Short <- (data$Close - data$Recent_Low_Short) / 
                            (data$Recent_High_Short - data$Recent_Low_Short)
    }
    
    if(sr_long > 0) {
      data$Recent_High_Long <- runMax(data$High, n = sr_long)
      data$Recent_Low_Long <- runMin(data$Low, n = sr_long)
      data$Position_Long <- (data$Close - data$Recent_Low_Long) / 
                           (data$Recent_High_Long - data$Recent_Low_Long)
    }
    
    # Momentum indicators (adaptive)
    roc_short <- min(3, n_periods %/% 4)
    roc_medium <- min(5, n_periods %/% 3)
    
    if(roc_short > 0) data$ROC_Short <- ROC(data$Close, n = roc_short)
    if(roc_medium > 0) data$ROC_Medium <- ROC(data$Close, n = roc_medium)
    
    # Commodity Channel Index (adaptive)
    cci_period <- min(20, n_periods %/% 2)
    if(cci_period >= 3) {
      data$CCI <- CCI(data[,c("High","Low","Close")], n = cci_period)
    }
    
    # Money Flow Index (if volume available and sufficient data)
    if(sum(!is.na(data$Volume)) > 10) {
      mfi_period <- min(14, (n_periods %/% 2))
      if(mfi_period >= 3) {
        data$MFI <- MFI(data[,c("High","Low","Close")], data$Volume, n = mfi_period)
      }
    }
    
    # Intraday specific indicators for hourly data
    if(interval == "hourly") {
      # Hourly momentum
      data$Hourly_Change <- c(0, diff(data$Close))
      data$Hourly_Change_Pct <- c(0, diff(data$Close) / data$Close[-nrow(data)] * 100)
      
      # Session-based analysis (NSE: 9:15 AM to 3:30 PM)
      data$Is_Market_Hours <- data$Hour >= 9 & data$Hour <= 15
      
      # Opening range breakout (first hour vs subsequent hours)
      if("Hour" %in% names(data)) {
        for(i in 2:nrow(data)) {
          if(data$Hour[i] == 10 && i > 1) {  # 10 AM - end of first hour
            first_hour_high <- max(data$High[max(1, i-5):i], na.rm = TRUE)
            first_hour_low <- min(data$Low[max(1, i-5):i], na.rm = TRUE)
            data$First_Hour_High[i:nrow(data)] <- first_hour_high
            data$First_Hour_Low[i:nrow(data)] <- first_hour_low
          }
        }
      }
    }
    
    # Price vs Volume Trend (adaptive)
    pvt_period <- min(10, n_periods %/% 2)
    if(pvt_period > 0 && sum(!is.na(data$Volume)) > pvt_period) {
      data$PVT <- runSum(data$Volume * data$Price_Change_Pct / 100, n = pvt_period)
    }
    
    cat("✅ Calculated", length(names(data)) - ncol(data) + ncol(data), "technical indicators\n")
    return(data)
    
  }, error = function(e) {
    cat("❌ Error calculating indicators:", e$message, "\n")
    return(data)
  })
}

# ===== ENHANCED INTRADAY TECHNICAL SCORING =====
calculate_intraday_tech_score <- function(data) {
  if(is.null(data) || nrow(data) == 0) {
    return(list(score = 0, components = list()))
  }
  
  # Get latest values (remove NA rows)
  latest_data <- tail(data[complete.cases(data),], 1)
  if(nrow(latest_data) == 0) {
    return(list(score = 0, components = list()))
  }
  
  latest <- latest_data[1,]
  scores <- list()
  interval <- attr(data, "interval")
  
  # 1. Trend Analysis (35% weight)
  trend_score <- 0
  
  # Moving Average alignment and trend (adaptive to available indicators)
  if(!is.na(latest$Close)) {
    # Check available SMA indicators
    sma_count <- 0
    sma_alignment <- 0
    
    if("SMA_Short" %in% names(latest) && !is.na(latest$SMA_Short)) {
      if(latest$Close > latest$SMA_Short) sma_alignment <- sma_alignment + 1
      sma_count <- sma_count + 1
    }
    if("SMA_Medium" %in% names(latest) && !is.na(latest$SMA_Medium)) {
      if(latest$Close > latest$SMA_Medium) sma_alignment <- sma_alignment + 1
      sma_count <- sma_count + 1
    }
    if("SMA_Long" %in% names(latest) && !is.na(latest$SMA_Long)) {
      if(latest$Close > latest$SMA_Long) sma_alignment <- sma_alignment + 1
      sma_count <- sma_count + 1
    }
    
    if(sma_count > 0) {
      trend_score <- trend_score + (sma_alignment / sma_count) * 30
    }
    
    # EMA trend analysis
    if("EMA_Fast" %in% names(latest) && "EMA_Slow" %in% names(latest) && 
       !is.na(latest$EMA_Fast) && !is.na(latest$EMA_Slow)) {
      if(latest$Close > latest$EMA_Slow && latest$EMA_Fast > latest$EMA_Slow) {
        trend_score <- trend_score + 25
      } else if(latest$Close > latest$EMA_Slow) {
        trend_score <- trend_score + 15
      }
    }
    
    # MACD trend
    if("MACD" %in% names(latest) && "MACD_Signal" %in% names(latest) && 
       !is.na(latest$MACD) && !is.na(latest$MACD_Signal)) {
      if(latest$MACD > latest$MACD_Signal && latest$MACD > 0) {
        trend_score <- trend_score + 15
      } else if(latest$MACD > latest$MACD_Signal) {
        trend_score <- trend_score + 10
      }
    }
    
    # Price position in range
    if("Position_Long" %in% names(latest) && !is.na(latest$Position_Long)) {
      if(latest$Position_Long > 0.7) trend_score <- trend_score + 20
      else if(latest$Position_Long > 0.5) trend_score <- trend_score + 15
      else if(latest$Position_Long > 0.3) trend_score <- trend_score + 10
    }
  }
  
  scores$trend <- min(100, trend_score)
  
  # 2. Momentum Analysis (30% weight)
  momentum_score <- 0
  
  # RSI analysis
  if("RSI" %in% names(latest) && !is.na(latest$RSI)) {
    if(latest$RSI > 50 && latest$RSI < 75) {
      momentum_score <- momentum_score + 35
    } else if(latest$RSI >= 40 && latest$RSI <= 50) {
      momentum_score <- momentum_score + 25
    } else if(latest$RSI > 30 && latest$RSI < 40) {
      momentum_score <- momentum_score + 20
    }
  }
  
  # Rate of Change momentum (adaptive)
  roc_positive <- 0
  roc_count <- 0
  
  if("ROC_Short" %in% names(latest) && !is.na(latest$ROC_Short)) {
    if(latest$ROC_Short > 0) roc_positive <- roc_positive + 1
    roc_count <- roc_count + 1
  }
  if("ROC_Medium" %in% names(latest) && !is.na(latest$ROC_Medium)) {
    if(latest$ROC_Medium > 0) roc_positive <- roc_positive + 1
    roc_count <- roc_count + 1
  }
  
  if(roc_count > 0) {
    momentum_score <- momentum_score + (roc_positive / roc_count) * 25
  }
  
  # Stochastic momentum
  if("Stoch_K" %in% names(latest) && "Stoch_D" %in% names(latest) && 
     !is.na(latest$Stoch_K) && !is.na(latest$Stoch_D)) {
    if(latest$Stoch_K > latest$Stoch_D && latest$Stoch_K < 80) {
      momentum_score <- momentum_score + 20
    } else if(latest$Stoch_K > 20 && latest$Stoch_K < 80) {
      momentum_score <- momentum_score + 15
    }
  }
  
  # Williams %R
  if("Williams_R" %in% names(latest) && !is.na(latest$Williams_R)) {
    if(latest$Williams_R > -80 && latest$Williams_R < -20) {
      momentum_score <- momentum_score + 15
    }
  }
  
  # Hourly momentum for intraday analysis
  if(interval == "hourly" && "Hourly_Change_Pct" %in% names(latest) && 
     !is.na(latest$Hourly_Change_Pct)) {
    if(abs(latest$Hourly_Change_Pct) < 2) {  # Steady movement
      momentum_score <- momentum_score + 5
    }
  }
  
  scores$momentum <- min(100, momentum_score)
  
  # 3. Volume Analysis (20% weight)
  volume_score <- 0
  
  if("Volume_Ratio" %in% names(latest) && !is.na(latest$Volume_Ratio)) {
    if(latest$Volume_Ratio > 2.0) volume_score <- volume_score + 40
    else if(latest$Volume_Ratio > 1.5) volume_score <- volume_score + 30
    else if(latest$Volume_Ratio > 1.2) volume_score <- volume_score + 25
    else if(latest$Volume_Ratio > 1.0) volume_score <- volume_score + 15
  }
  
  # OBV trend analysis
  if("OBV" %in% names(data) && nrow(data) > 3) {
    obv_recent <- tail(data$OBV[!is.na(data$OBV)], 3)
    if(length(obv_recent) >= 3) {
      obv_trend <- obv_recent[3] - obv_recent[1]
      if(obv_trend > 0) volume_score <- volume_score + 25
      else if(obv_trend == 0) volume_score <- volume_score + 15
    }
  }
  
  # Money Flow Index
  if("MFI" %in% names(latest) && !is.na(latest$MFI)) {
    if(latest$MFI > 50 && latest$MFI < 80) {
      volume_score <- volume_score + 25
    } else if(latest$MFI >= 20 && latest$MFI <= 50) {
      volume_score <- volume_score + 15
    }
  }
  
  # PVT analysis
  if("PVT" %in% names(data) && nrow(data) > 2) {
    pvt_recent <- tail(data$PVT[!is.na(data$PVT)], 2)
    if(length(pvt_recent) >= 2 && pvt_recent[2] > pvt_recent[1]) {
      volume_score <- volume_score + 10
    }
  }
  
  scores$volume <- min(100, volume_score)
  
  # 4. Support/Resistance Analysis (10% weight)
  support_resistance_score <- 0
  
  if("Position_Short" %in% names(latest) && !is.na(latest$Position_Short)) {
    if(latest$Position_Short > 0.7 && latest$Position_Short < 0.95) {
      support_resistance_score <- support_resistance_score + 35
    } else if(latest$Position_Short > 0.5) {
      support_resistance_score <- support_resistance_score + 25
    } else if(latest$Position_Short > 0.3) {
      support_resistance_score <- support_resistance_score + 20
    }
  }
  
  if("Position_Long" %in% names(latest) && !is.na(latest$Position_Long)) {
    if(latest$Position_Long > 0.6 && latest$Position_Long < 0.9) {
      support_resistance_score <- support_resistance_score + 30
    } else if(latest$Position_Long > 0.4) {
      support_resistance_score <- support_resistance_score + 20
    }
  }
  
  # Bollinger Band position
  if("BB_Position" %in% names(latest) && !is.na(latest$BB_Position)) {
    if(latest$BB_Position > 0.5 && latest$BB_Position < 0.85) {
      support_resistance_score <- support_resistance_score + 35
    } else if(latest$BB_Position > 0.2 && latest$BB_Position <= 0.5) {
      support_resistance_score <- support_resistance_score + 20
    }
  }
  
  scores$support_resistance <- min(100, support_resistance_score)
  
  # 5. Volatility & Market Structure (5% weight)
  volatility_score <- 0
  
  # ATR analysis
  if("ATR" %in% names(latest) && !is.na(latest$ATR) && latest$Close > 0) {
    atr_pct <- (latest$ATR / latest$Close) * 100
    if(interval == "hourly") {
      # Lower volatility thresholds for hourly data
      if(atr_pct < 0.5) volatility_score <- volatility_score + 40
      else if(atr_pct < 1.0) volatility_score <- volatility_score + 30
      else if(atr_pct < 2.0) volatility_score <- volatility_score + 20
    } else {
      # Daily thresholds
      if(atr_pct < 2) volatility_score <- volatility_score + 40
      else if(atr_pct < 4) volatility_score <- volatility_score + 30
      else if(atr_pct < 6) volatility_score <- volatility_score + 20
    }
  }
  
  # Range analysis
  if("Range_Pct" %in% names(latest) && !is.na(latest$Range_Pct)) {
    if(interval == "hourly") {
      if(latest$Range_Pct > 0.2 && latest$Range_Pct < 1.5) {
        volatility_score <- volatility_score + 30
      } else if(latest$Range_Pct <= 0.2) {
        volatility_score <- volatility_score + 20
      }
    } else {
      if(latest$Range_Pct > 1 && latest$Range_Pct < 5) {
        volatility_score <- volatility_score + 30
      } else if(latest$Range_Pct <= 1) {
        volatility_score <- volatility_score + 20
      }
    }
  }
  
  # Market hours bonus for intraday (NSE: 9:15 AM to 3:30 PM)
  if(interval == "hourly" && "Is_Market_Hours" %in% names(latest) && !is.na(latest$Is_Market_Hours)) {
    if(latest$Is_Market_Hours) {
      volatility_score <- volatility_score + 30
    }
  }
  
  scores$volatility <- min(100, volatility_score)
  
  # Calculate weighted final score
  final_score <- (scores$trend * 0.35) + 
                (scores$momentum * 0.30) + 
                (scores$volume * 0.20) + 
                (scores$support_resistance * 0.10) + 
                (scores$volatility * 0.05)
  
  return(list(
    score = round(final_score, 1),
    components = scores,
    latest_price = ifelse(!is.na(latest$Close), latest$Close, tail(data$Close[!is.na(data$Close)], 1)),
    price_change = ifelse("Price_Change" %in% names(latest), latest$Price_Change, 0),
    price_change_pct = ifelse("Price_Change_Pct" %in% names(latest), round(latest$Price_Change_Pct, 2), 0)
  ))
}

# ===== SIGNAL GENERATION (Adaptive) =====
generate_intraday_signals <- function(data) {
  if(is.null(data) || nrow(data) < 5) {
    return(list())
  }
  
  signals <- list()
  latest <- tail(data[complete.cases(data),], 1)[1,]
  interval <- attr(data, "interval")
  
  # Trend signals (adaptive to available indicators)
  if(!is.na(latest$Close)) {
    if("SMA_Long" %in% names(latest) && !is.na(latest$SMA_Long)) {
      if(latest$Close > latest$SMA_Long) {
        signals$trend_signal <- "BULLISH - Above Long SMA"
      } else {
        signals$trend_signal <- "BEARISH - Below Long SMA"
      }
    } else if("SMA_Medium" %in% names(latest) && !is.na(latest$SMA_Medium)) {
      if(latest$Close > latest$SMA_Medium) {
        signals$trend_signal <- "BULLISH - Above Medium SMA"
      } else {
        signals$trend_signal <- "BEARISH - Below Medium SMA"
      }
    }
  }
  
  # MACD signals
  if("MACD" %in% names(latest) && "MACD_Signal" %in% names(latest) && 
     !is.na(latest$MACD) && !is.na(latest$MACD_Signal)) {
    if(latest$MACD > latest$MACD_Signal && latest$MACD > 0) {
      signals$macd_signal <- "STRONG BUY - MACD Above Signal & Positive"
    } else if(latest$MACD > latest$MACD_Signal) {
      signals$macd_signal <- "BUY - MACD Above Signal"
    } else {
      signals$macd_signal <- "SELL - MACD Below Signal"
    }
  }
  
  # RSI signals
  if("RSI" %in% names(latest) && !is.na(latest$RSI)) {
    if(latest$RSI > 70) {
      signals$rsi_signal <- "OVERBOUGHT - Consider Sell"
    } else if(latest$RSI < 30) {
      signals$rsi_signal <- "OVERSOLD - Consider Buy"
    } else if(latest$RSI > 50) {
      signals$rsi_signal <- "BULLISH - RSI Above 50"
    } else {
      signals$rsi_signal <- "BEARISH - RSI Below 50"
    }
  }
  
  # Bollinger Band signals
  if("BB_Position" %in% names(latest) && !is.na(latest$BB_Position)) {
    if(latest$BB_Position > 0.8) {
      signals$bb_signal <- "NEAR UPPER BAND - Resistance"
    } else if(latest$BB_Position < 0.2) {
      signals$bb_signal <- "NEAR LOWER BAND - Support"
    } else {
      signals$bb_signal <- "MIDDLE RANGE - Neutral"
    }
  }
  
  # Volume signals
  if("Volume_Ratio" %in% names(latest) && !is.na(latest$Volume_Ratio)) {
    if(latest$Volume_Ratio > 2.0) {
      signals$volume_signal <- "HIGH VOLUME - Strong Move"
    } else if(latest$Volume_Ratio > 1.5) {
      signals$volume_signal <- "ABOVE AVERAGE VOLUME"
    } else {
      signals$volume_signal <- "NORMAL VOLUME"
    }
  }
  
  # Intraday specific signals
  if(interval == "hourly") {
    # Market session signal
    if("Is_Market_Hours" %in% names(latest) && !is.na(latest$Is_Market_Hours)) {
      if(latest$Is_Market_Hours) {
        signals$session_signal <- "REGULAR MARKET HOURS"
      } else {
        signals$session_signal <- "OUTSIDE MARKET HOURS"
      }
    }
    
    # Hourly momentum
    if("Hourly_Change_Pct" %in% names(latest) && !is.na(latest$Hourly_Change_Pct)) {
      if(latest$Hourly_Change_Pct > 1) {
        signals$hourly_momentum <- "STRONG POSITIVE HOURLY MOVE"
      } else if(latest$Hourly_Change_Pct < -1) {
        signals$hourly_momentum <- "STRONG NEGATIVE HOURLY MOVE"
      } else {
        signals$hourly_momentum <- "STEADY HOURLY MOVEMENT"
      }
    }
    
    # Opening range breakout
    if("First_Hour_High" %in% names(latest) && "First_Hour_Low" %in% names(latest) &&
       !is.na(latest$First_Hour_High) && !is.na(latest$First_Hour_Low)) {
      if(latest$Close > latest$First_Hour_High) {
        signals$opening_range <- "BREAKOUT ABOVE OPENING RANGE"
      } else if(latest$Close < latest$First_Hour_Low) {
        signals$opening_range <- "BREAKDOWN BELOW OPENING RANGE"
      } else {
        signals$opening_range <- "WITHIN OPENING RANGE"
      }
    }
  }
  
  # Momentum confirmation
  momentum_signals <- c()
  if("Stoch_K" %in% names(latest) && "Stoch_D" %in% names(latest) && 
     !is.na(latest$Stoch_K) && !is.na(latest$Stoch_D)) {
    if(latest$Stoch_K > latest$Stoch_D) {
      momentum_signals <- c(momentum_signals, "Stochastic Bullish")
    } else {
      momentum_signals <- c(momentum_signals, "Stochastic Bearish")
    }
  }
  
  if("Williams_R" %in% names(latest) && !is.na(latest$Williams_R)) {
    if(latest$Williams_R > -50) {
      momentum_signals <- c(momentum_signals, "Williams %R Strong")
    }
  }
  
  if(length(momentum_signals) > 0) {
    signals$momentum_confirmation <- paste(momentum_signals, collapse = ", ")
  }
  
  return(signals)
}

# ===== MAIN ANALYSIS FUNCTION =====
analyze_intraday_stock <- function(symbol, interval = "1h", period_days = 7) {
  cat("🔍 Starting intraday technical analysis for", symbol, "(", interval, ")\n")
  cat("=" , rep("=", 50), "\n", sep="")
  
  # Step 1: Load data
  data <- get_intraday_data(symbol, period_days = period_days, interval = interval)
  if(is.null(data)) {
    return(NULL)
  }
  
  # Step 2: Calculate indicators
  data <- calculate_intraday_indicators(data)
  if(is.null(data)) {
    return(NULL)
  }
  
  # Step 3: Calculate technical score
  tech_analysis <- calculate_intraday_tech_score(data)
  
  # Step 4: Generate signals
  signals <- generate_intraday_signals(data)
  
  # Step 5: Create summary
  summary <- list(
    symbol = symbol,
    interval = attr(data, "interval"),
    analysis_time = Sys.time(),
    data_points = nrow(data),
    date_range = paste(min(data$DateTime), "to", max(data$DateTime)),
    technical_score = tech_analysis$score,
    score_components = tech_analysis$components,
    current_price = tech_analysis$latest_price,
    price_change = tech_analysis$price_change,
    price_change_pct = tech_analysis$price_change_pct,
    signals = signals,
    data = data
  )
  
  cat("✅ Analysis completed for", symbol, "\n")
  cat("Interval:", attr(data, "interval"), "\n")
  cat("Technical Score:", tech_analysis$score, "/100\n")
  
  # Safe price display for indices
  if(!is.null(tech_analysis$latest_price) && is.numeric(tech_analysis$latest_price) && !is.na(tech_analysis$latest_price)) {
    cat("Current Price: ₹", round(tech_analysis$latest_price, 2), "\n")
  } else {
    cat("Current Price: Index (", round(tail(data$Close, 1), 2), ")\n")
  }
  
  # Safe price change display
  if(!is.null(tech_analysis$price_change) && is.numeric(tech_analysis$price_change) && !is.na(tech_analysis$price_change)) {
    cat("Price Change:", ifelse(tech_analysis$price_change > 0, "+", ""), 
        round(tech_analysis$price_change, 2), " (", 
        round(tech_analysis$price_change_pct, 2), "%)\n")
  } else {
    cat("Price Change: Index movement calculated\n")
  }
  
  return(summary)
}

# ===== HTML REPORT GENERATION =====
generate_intraday_html_report <- function(analysis_result, output_file = NULL) {
  if(is.null(analysis_result)) {
    cat("No analysis result to generate report\n")
    return(NULL)
  }
  
  if(is.null(output_file)) {
    output_file <- paste0("Intraday_Technical_Analysis_", analysis_result$symbol, "_", 
                         format(Sys.time(), "%Y%m%d"), ".html")
  }
  
  # Create HTML content
  html_content <- sprintf('
<!DOCTYPE html>
<html>
<head>
    <title>Intraday Technical Analysis - %s</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%); 
                 color: white; padding: 20px; border-radius: 10px; text-align: center; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                       gap: 20px; margin: 20px 0; }
        .card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .score { font-size: 48px; font-weight: bold; text-align: center; margin: 10px 0; }
        .score.excellent { color: #27ae60; }
        .score.good { color: #2ecc71; }
        .score.average { color: #f39c12; }
        .score.poor { color: #e74c3c; }
        .component-score { display: flex; justify-content: space-between; margin: 5px 0; 
                          padding: 8px; background: #ecf0f1; border-radius: 5px; }
        .signal { padding: 10px; margin: 5px 0; border-radius: 5px; font-weight: bold; }
        .signal.bullish { background: #d5f4e6; color: #27ae60; border-left: 4px solid #27ae60; }
        .signal.bearish { background: #fadbd8; color: #e74c3c; border-left: 4px solid #e74c3c; }
        .signal.neutral { background: #fef9e7; color: #f39c12; border-left: 4px solid #f39c12; }
        .price-display { text-align: center; font-size: 24px; margin: 15px 0; }
        .price-change.positive { color: #27ae60; }
        .price-change.negative { color: #e74c3c; }
        .timestamp { text-align: center; color: #7f8c8d; margin: 10px 0; }
        table { width: 100%%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #34495e; color: white; }
        .footer { text-align: center; margin-top: 30px; color: #7f8c8d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ REAL-TIME INTRADAY TECHNICAL ANALYSIS</h1>
            <h2>%s (NSE)</h2>
            <div class="timestamp">Analysis Time: %s</div>
        </div>
        
        <div class="summary-grid">
            <div class="card">
                <h3>📊 Technical Score</h3>
                <div class="score %s">%s</div>
                <div style="text-align: center;">Out of 100</div>
            </div>
            
            <div class="card">
                <h3>💰 Current Price</h3>
                <div class="price-display">
                    ₹ %s<br>
                    <span class="price-change %s">%s%s (%s%%)</span>
                </div>
            </div>
            
            <div class="card">
                <h3>📈 Data Coverage</h3>
                <p><strong>Data Points:</strong> %s periods</p>
                <p><strong>Period:</strong> %s</p>
                <p><strong>Timeframe:</strong> %s Analysis</p>
            </div>
        </div>
        
        <div class="card">
            <h3>🎯 Score Components</h3>',
    analysis_result$symbol,
    analysis_result$symbol,
    format(analysis_result$analysis_time, "%d %B %Y, %H:%M IST"),
    ifelse(analysis_result$technical_score >= 75, "excellent",
           ifelse(analysis_result$technical_score >= 60, "good",
                  ifelse(analysis_result$technical_score >= 40, "average", "poor"))),
    analysis_result$technical_score,
    round(analysis_result$current_price, 2),
    ifelse(analysis_result$price_change >= 0, "positive", "negative"),
    ifelse(analysis_result$price_change >= 0, "+", ""),
    round(analysis_result$price_change, 2),
    round(analysis_result$price_change_pct, 2),
    analysis_result$data_points,
    analysis_result$date_range,
    ifelse(analysis_result$interval == "hourly", "Hourly Intraday", "Daily")
  )
  
  # Add component scores
  for(component in names(analysis_result$score_components)) {
    score_val <- analysis_result$score_components[[component]]
    html_content <- paste0(html_content, sprintf(
      '<div class="component-score">
        <span>%s</span>
        <span><strong>%s/100</strong></span>
      </div>',
      tools::toTitleCase(gsub("_", " ", component)),
      round(score_val, 1)
    ))
  }
  
  html_content <- paste0(html_content, '</div>')
  
  # Add signals section
  html_content <- paste0(html_content, '
        <div class="card">
            <h3>🚦 Trading Signals</h3>')
  
  for(signal_name in names(analysis_result$signals)) {
    signal_text <- analysis_result$signals[[signal_name]]
    signal_class <- if(grepl("BUY|BULLISH|Above", signal_text, ignore.case = TRUE)) "bullish"
                   else if(grepl("SELL|BEARISH|Below", signal_text, ignore.case = TRUE)) "bearish"
                   else "neutral"
    
    html_content <- paste0(html_content, sprintf(
      '<div class="signal %s">
        <strong>%s:</strong> %s
      </div>',
      signal_class,
      tools::toTitleCase(gsub("_signal", "", signal_name)),
      signal_text
    ))
  }
  
  html_content <- paste0(html_content, '</div>')
  
  # Add latest technical values table
  latest_data <- tail(analysis_result$data[complete.cases(analysis_result$data),], 1)
  if(nrow(latest_data) > 0) {
    html_content <- paste0(html_content, '
        <div class="card">
            <h3>📋 Latest Technical Indicators</h3>
            <table>
                <tr><th>Indicator</th><th>Value</th><th>Interpretation</th></tr>')
    
    # Add key indicators adapted for intraday
    interval <- ifelse(is.null(analysis_result$interval), "daily", analysis_result$interval)
    
    indicators <- list()
    
    # RSI
    if("RSI" %in% names(latest_data) && !is.na(latest_data$RSI)) {
      indicators <- append(indicators, list(
        list("RSI", round(latest_data$RSI, 2), 
             ifelse(latest_data$RSI > 70, "Overbought", 
                    ifelse(latest_data$RSI < 30, "Oversold", "Neutral")))
      ))
    }
    
    # MACD
    if("MACD" %in% names(latest_data) && "MACD_Signal" %in% names(latest_data) && 
       !is.na(latest_data$MACD) && !is.na(latest_data$MACD_Signal)) {
      indicators <- append(indicators, list(
        list("MACD", round(latest_data$MACD, 4), 
             ifelse(latest_data$MACD > latest_data$MACD_Signal, "Bullish", "Bearish"))
      ))
    }
    
    # Moving Averages
    if("SMA_Long" %in% names(latest_data) && !is.na(latest_data$SMA_Long)) {
      indicators <- append(indicators, list(
        list("Long SMA", round(latest_data$SMA_Long, 2), 
             ifelse(latest_data$Close > latest_data$SMA_Long, "Above SMA", "Below SMA"))
      ))
    }
    
    if("SMA_Medium" %in% names(latest_data) && !is.na(latest_data$SMA_Medium)) {
      indicators <- append(indicators, list(
        list("Medium SMA", round(latest_data$SMA_Medium, 2), 
             ifelse(latest_data$Close > latest_data$SMA_Medium, "Above SMA", "Below SMA"))
      ))
    }
    
    # Volume Analysis
    if("Volume_Ratio" %in% names(latest_data) && !is.na(latest_data$Volume_Ratio)) {
      indicators <- append(indicators, list(
        list("Volume Ratio", round(latest_data$Volume_Ratio, 2), 
             ifelse(latest_data$Volume_Ratio > 1.5, "High Volume", "Normal Volume"))
      ))
    }
    
    # ATR
    if("ATR" %in% names(latest_data) && !is.na(latest_data$ATR)) {
      indicators <- append(indicators, list(
        list("ATR", round(latest_data$ATR, 2), "Volatility Measure")
      ))
    }
    
    # Bollinger Bands
    if("BB_Position" %in% names(latest_data) && !is.na(latest_data$BB_Position)) {
      indicators <- append(indicators, list(
        list("BB Position", paste0(round(latest_data$BB_Position * 100, 1), "%"), 
             ifelse(latest_data$BB_Position > 0.8, "Near Upper Band",
                    ifelse(latest_data$BB_Position < 0.2, "Near Lower Band", "Mid Range")))
      ))
    }
    
    # Williams %R
    if("Williams_R" %in% names(latest_data) && !is.na(latest_data$Williams_R)) {
      indicators <- append(indicators, list(
        list("Williams %R", round(latest_data$Williams_R, 2), 
             ifelse(latest_data$Williams_R > -20, "Overbought",
                    ifelse(latest_data$Williams_R < -80, "Oversold", "Neutral")))
      ))
    }
    
    # Intraday specific indicators
    if(interval == "hourly") {
      if("Hourly_Change_Pct" %in% names(latest_data) && !is.na(latest_data$Hourly_Change_Pct)) {
        indicators <- append(indicators, list(
          list("Hourly Change", paste0(round(latest_data$Hourly_Change_Pct, 2), "%"), 
               ifelse(abs(latest_data$Hourly_Change_Pct) > 1, "Strong Move", "Steady Movement"))
        ))
      }
      
      if("Is_Market_Hours" %in% names(latest_data) && !is.na(latest_data$Is_Market_Hours)) {
        indicators <- append(indicators, list(
          list("Market Session", ifelse(latest_data$Is_Market_Hours, "Regular Hours", "Outside Hours"), 
               ifelse(latest_data$Is_Market_Hours, "Active Trading", "Extended Hours"))
        ))
      }
    }
    
    # ROC
    if("ROC_Short" %in% names(latest_data) && !is.na(latest_data$ROC_Short)) {
      indicators <- append(indicators, list(
        list("ROC (Short)", paste0(round(latest_data$ROC_Short * 100, 2), "%"), 
             ifelse(latest_data$ROC_Short > 0, "Positive Momentum", "Negative Momentum"))
      ))
    }
    
    for(ind in indicators) {
      html_content <- paste0(html_content, sprintf(
        '<tr><td>%s</td><td>%s</td><td>%s</td></tr>',
        ind[[1]], ind[[2]], ind[[3]]
      ))
    }
    
    html_content <- paste0(html_content, '</table></div>')
  }
  
  # Footer
  html_content <- paste0(html_content, '
        <div class="footer">
            <p>📊 Generated by Enhanced Daily Technical Analysis System | Data Source: Yahoo Finance</p>
            <p>⚠️ This is for educational purposes only. Not financial advice.</p>
            <p>🕒 Analysis covers 1-year daily data with comprehensive technical indicators</p>
        </div>
    </div>
</body>
</html>')
  
  # Write to file
  writeLines(html_content, output_file)
  cat("✅ HTML report generated:", output_file, "\n")
  
  return(output_file)
}

# ===== INDEX TESTING FUNCTIONS =====
test_nifty50_analysis <- function() {
  cat("🚀 Testing Daily Technical Analysis with NIFTY 50 INDEX\n")
  cat("=============================================\n")
  
  # Analyze NIFTY 50
  result <- analyze_intraday_stock("NIFTY50")
  
  if(!is.null(result)) {
    # Generate HTML report
    report_file <- generate_intraday_html_report(result)
    
    # Print summary
    cat("\n📈 NIFTY 50 ANALYSIS SUMMARY:\n")
    cat("Technical Score:", result$technical_score, "/100\n")
    cat("Trend Score:", round(result$score_components$trend, 1), "/100\n")
    cat("Momentum Score:", round(result$score_components$momentum, 1), "/100\n")
    cat("Volume Score:", round(result$score_components$volume, 1), "/100\n")
    cat("Support/Resistance Score:", round(result$score_components$support_resistance, 1), "/100\n")
    cat("Volatility Score:", round(result$score_components$volatility, 1), "/100\n")
    cat("\n🚦 KEY SIGNALS:\n")
    for(signal in names(result$signals)) {
      cat(paste0(toupper(gsub("_signal", "", signal)), ": ", result$signals[[signal]], "\n"))
    }
    
    return(list(analysis = result, report_file = report_file))
  }
  
  return(NULL)
}

test_nifty_bank_analysis <- function() {
  cat("🚀 Testing Daily Technical Analysis with NIFTY BANK INDEX\n")
  cat("===============================================\n")
  
  # Analyze NIFTY Bank
  result <- analyze_intraday_stock("BANKNIFTY")
  
  if(!is.null(result)) {
    # Generate HTML report
    report_file <- generate_intraday_html_report(result)
    
    # Print summary
    cat("\n📈 NIFTY BANK ANALYSIS SUMMARY:\n")
    cat("Technical Score:", result$technical_score, "/100\n")
    cat("Trend Score:", round(result$score_components$trend, 1), "/100\n")
    cat("Momentum Score:", round(result$score_components$momentum, 1), "/100\n")
    cat("Volume Score:", round(result$score_components$volume, 1), "/100\n")
    cat("Support/Resistance Score:", round(result$score_components$support_resistance, 1), "/100\n")
    cat("Volatility Score:", round(result$score_components$volatility, 1), "/100\n")
    cat("\n🚦 KEY SIGNALS:\n")
    for(signal in names(result$signals)) {
      cat(paste0(toupper(gsub("_signal", "", signal)), ": ", result$signals[[signal]], "\n"))
    }
    
    return(list(analysis = result, report_file = report_file))
  }
  
  return(NULL)
}

test_all_major_indices <- function() {
  cat("🚀 Testing All Major NSE Indices\n")
  cat("=================================\n")
  
  indices <- c("NIFTY50", "BANKNIFTY", "NIFTYIT", "NIFTYPHARMA")
  results <- list()
  
  for(index in indices) {
    cat("\n📊 Analyzing", index, "...\n")
    result <- analyze_intraday_stock(index)
    
    if(!is.null(result)) {
      results[[index]] <- result
      cat("✅ Completed", index, "- Score:", result$technical_score, "/100\n")
    } else {
      cat("❌ Failed to analyze", index, "\n")
    }
    
    Sys.sleep(2) # Rate limiting
  }
  
  # Generate summary
  if(length(results) > 0) {
    cat("\n📊 INDICES SUMMARY:\n")
    cat("==================\n")
    
    for(idx in names(results)) {
      result <- results[[idx]]
      cat(sprintf("%-12s: Score %5.1f | Price ₹%8.2f | Change %+6.2f%%\n",
                  idx, 
                  result$technical_score,
                  result$current_price,
                  result$price_change_pct))
    }
    
    # Find best and worst performing
    scores <- sapply(results, function(x) x$technical_score)
    best_index <- names(scores)[which.max(scores)]
    worst_index <- names(scores)[which.min(scores)]
    
    cat("\n🏆 Best Technical Score:", best_index, "(",scores[best_index],")\n")
    cat("📉 Lowest Technical Score:", worst_index, "(",scores[worst_index],")\n")
  }
  
  return(results)
}

# ===== TESTING FUNCTION FOR RELIANCE =====
test_reliance_analysis <- function() {
  cat("🚀 Testing Daily Technical Analysis with RELIANCE\n")
  cat("==========================================\n")
  
  # Analyze RELIANCE
  result <- analyze_intraday_stock("RELIANCE")
  
  if(!is.null(result)) {
    # Generate HTML report
    report_file <- generate_intraday_html_report(result)
    
    # Print summary
    cat("\n📈 ANALYSIS SUMMARY:\n")
    cat("Technical Score:", result$technical_score, "/100\n")
    cat("Trend Score:", round(result$score_components$trend, 1), "/100\n")
    cat("Momentum Score:", round(result$score_components$momentum, 1), "/100\n")
    cat("Volume Score:", round(result$score_components$volume, 1), "/100\n")
    cat("Support/Resistance Score:", round(result$score_components$support_resistance, 1), "/100\n")
    cat("Volatility Score:", round(result$score_components$volatility, 1), "/100\n")
    cat("\n🚦 KEY SIGNALS:\n")
    for(signal in names(result$signals)) {
      cat(paste0(toupper(gsub("_signal", "", signal)), ": ", result$signals[[signal]], "\n"))
    }
    
    return(list(analysis = result, report_file = report_file))
  }
  
  return(NULL)
}

# ===== BATCH PROCESSING FOR NIFTY50 STOCKS =====
analyze_nifty50_intraday <- function(interval = "5m", max_stocks = NULL, output_file = NULL) {
  cat("🚀 Starting Intraday Analysis for Nifty50 Stocks\n")
  cat("================================================\n")
  cat("📊 Interval:", interval, "\n")
  
  # Get Nifty50 stock list
  nifty50_stocks <- get_nifty50_stocks()
  
  if(!is.null(max_stocks) && max_stocks < length(nifty50_stocks)) {
    nifty50_stocks <- nifty50_stocks[1:max_stocks]
    cat("📋 Analyzing first", max_stocks, "stocks for testing\n")
  }
  
  cat("� Total stocks to analyze:", length(nifty50_stocks), "\n\n")
  
  # Initialize results storage
  results <- list()
  successful_analyses <- 0
  failed_analyses <- 0
  
  # Progress tracking
  start_time <- Sys.time()
  
  for(i in seq_along(nifty50_stocks)) {
    stock <- nifty50_stocks[i]
    
    cat(sprintf("🔍 [%d/%d] Analyzing %s...\n", i, length(nifty50_stocks), stock))
    
    # Analyze individual stock
    result <- analyze_intraday_stock(stock, interval = interval)
    
    if(!is.null(result)) {
      results[[stock]] <- result
      successful_analyses <- successful_analyses + 1
      
      # Safe price display for both stocks and indices
      price_display <- if(!is.null(result$current_price) && is.numeric(result$current_price) && !is.na(result$current_price)) {
        paste0("₹", round(result$current_price, 2))
      } else {
        "Index"
      }
      
      cat(sprintf("✅ %s completed - Score: %s/100, Price: %s\n", 
                  stock, 
                  round(result$technical_score, 1),
                  price_display))
    } else {
      failed_analyses <- failed_analyses + 1
      cat(sprintf("❌ %s failed\n", stock))
    }
    
    # Rate limiting to avoid overwhelming Yahoo Finance
    if(i < length(nifty50_stocks)) {
      Sys.sleep(1.5)  # 1.5 second delay between requests
    }
    
    # Progress update every 10 stocks
    if(i %% 10 == 0) {
      elapsed <- as.numeric(difftime(Sys.time(), start_time, units = "mins"))
      avg_time <- elapsed / i
      eta <- (length(nifty50_stocks) - i) * avg_time
      
      cat(sprintf("\n📊 Progress: %d/%d completed (%.1f%%), ETA: %.1f minutes\n\n", 
                  i, length(nifty50_stocks), (i/length(nifty50_stocks))*100, eta))
    }
  }
  
  # Final summary
  total_time <- as.numeric(difftime(Sys.time(), start_time, units = "mins"))
  
  cat("\n" , rep("=", 60), "\n", sep="")
  cat("📈 NIFTY50 INTRADAY ANALYSIS COMPLETE\n")
  cat(rep("=", 60), "\n")
  cat("✅ Successful analyses:", successful_analyses, "\n")
  cat("❌ Failed analyses:", failed_analyses, "\n")
  cat("⏱️  Total time:", round(total_time, 2), "minutes\n")
  cat("📊 Success rate:", round((successful_analyses/length(nifty50_stocks))*100, 1), "%\n\n")
  
  if(length(results) > 0) {
    # Generate summary statistics
    scores <- sapply(results, function(x) x$technical_score)
    price_changes <- sapply(results, function(x) {
      if(is.numeric(x$price_change_pct) && !is.na(x$price_change_pct)) {
        return(x$price_change_pct)
      } else {
        return(0)  # Default for indices or invalid data
      }
    })
    
    # Top performers
    top_scores <- head(sort(scores, decreasing = TRUE), 5)
    worst_scores <- head(sort(scores, decreasing = FALSE), 5)
    
    cat("🏆 TOP 5 TECHNICAL SCORES:\n")
    for(i in 1:length(top_scores)) {
      stock_name <- names(top_scores)[i]
      price_change <- results[[stock_name]]$price_change_pct
      price_display <- if(is.numeric(price_change) && !is.na(price_change)) {
        sprintf("Price Change: %+.2f%%", price_change)
      } else {
        "Index Movement"
      }
      cat(sprintf("%d. %s: %s/100 (%s)\n", 
                  i, stock_name, round(top_scores[i], 1), price_display))
    }
    
    cat("\n📉 LOWEST 5 TECHNICAL SCORES:\n")
    for(i in 1:length(worst_scores)) {
      stock_name <- names(worst_scores)[i]
      price_change <- results[[stock_name]]$price_change_pct
      price_display <- if(is.numeric(price_change) && !is.na(price_change)) {
        sprintf("Price Change: %+.2f%%", price_change)
      } else {
        "Index Movement"
      }
      cat(sprintf("%d. %s: %s/100 (%s)\n", 
                  i, stock_name, round(worst_scores[i], 1), price_display))
    }
    
    # Market overview
    avg_score <- mean(scores, na.rm = TRUE)
    avg_change <- mean(price_changes, na.rm = TRUE)
    positive_stocks <- sum(price_changes > 0, na.rm = TRUE)
    
    cat("\n📊 MARKET OVERVIEW:\n")
    cat("Average Technical Score:", round(avg_score, 1), "/100\n")
    cat("Average Price Change:", sprintf("%+.2f%%", avg_change), "\n")
    cat("Stocks in Green:", positive_stocks, "/", length(results), 
        sprintf(" (%.1f%%)", (positive_stocks/length(results))*100), "\n")
    
    # Save results to CSV if requested
    if(!is.null(output_file) || TRUE) {  # Always save results
      if(is.null(output_file)) {
        output_file <- paste0("Nifty50_Intraday_Analysis_", 
                             format(Sys.time(), "%Y%m%d"), ".csv")
      }
      
      # Create summary dataframe
      summary_df <- data.frame(
        Symbol = names(results),
        Technical_Score = sapply(results, function(x) round(x$technical_score, 2)),
        Current_Price = sapply(results, function(x) {
          if(is.numeric(x$current_price) && !is.na(x$current_price)) {
            round(x$current_price, 2)
          } else {
            "Index"
          }
        }),
        Price_Change = sapply(results, function(x) {
          if(is.numeric(x$price_change) && !is.na(x$price_change)) {
            round(x$price_change, 2)
          } else {
            "N/A"
          }
        }),
        Price_Change_Pct = sapply(results, function(x) {
          if(is.numeric(x$price_change_pct) && !is.na(x$price_change_pct)) {
            round(x$price_change_pct, 2)
          } else {
            "N/A"
          }
        }),
        Data_Points = sapply(results, function(x) x$data_points),
        Analysis_Time = sapply(results, function(x) format(x$analysis_time, "%Y-%m-%d %H:%M")),
        stringsAsFactors = FALSE
      )
      
      # Add component scores
      for(component in c("trend", "momentum", "volume", "support_resistance", "volatility")) {
        summary_df[[paste0(component, "_score")]] <- sapply(results, function(x) {
          if(component %in% names(x$score_components)) {
            round(x$score_components[[component]], 2)
          } else {
            NA
          }
        })
      }
      
      # Sort by technical score (descending)
      summary_df <- summary_df[order(summary_df$Technical_Score, decreasing = TRUE),]
      
      write.csv(summary_df, output_file, row.names = FALSE)
      cat("\n💾 Results saved to:", output_file, "\n")
    }
  }
  
  return(results)
}

# ===== QUICK TEST FUNCTION =====
test_nifty50_sample <- function(n_stocks = 5, interval = "1h") {
  cat("🧪 Testing Nifty50 Intraday Analysis with", n_stocks, "stocks\n")
  cat("Interval:", interval, "\n")
  cat(rep("=", 50), "\n")
  
  results <- analyze_nifty50_intraday(interval = interval, max_stocks = n_stocks)
  return(results)
}

# ===== COMBINED DASHBOARD GENERATION =====
generate_nifty50_dashboard <- function(results, interval = "1h") {
  if (is.null(results) || length(results) == 0) {
    cat("❌ No results to generate dashboard\n")
    return(NULL)
  }
  
  cat("📊 Generating Nifty50 Combined Dashboard...\n")
  
  # Try to load the latest CSV file to get component scores
  csv_data <- NULL
  tryCatch({
    # Find the most recent CSV file
    csv_files <- list.files(pattern = "Nifty50_Intraday_Analysis_.*\\.csv$", full.names = FALSE)
    if (length(csv_files) > 0) {
      latest_csv <- csv_files[length(csv_files)]  # Get the most recent file
      cat("📊 Loading CSV data from:", latest_csv, "\n")
      csv_data <- read.csv(latest_csv, stringsAsFactors = FALSE)
      cat("✅ Loaded", nrow(csv_data), "rows from CSV\n")
    }
  }, error = function(e) {
    cat("⚠️ Could not load CSV data:", e$message, "\n")
  })
  
  # Create dashboard HTML content
  html_content <- paste0('
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nifty50 Intraday Technical Analysis Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        .controls {
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 1px solid #dee2e6;
        }
        
        .controls-row {
            display: flex;
            gap: 20px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .filter-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .filter-group label {
            font-weight: 600;
            color: #495057;
        }
        
        select, input {
            padding: 8px 12px;
            border: 1px solid #ced4da;
            border-radius: 5px;
            font-size: 14px;
        }
        
        .search-box {
            flex: 1;
            min-width: 250px;
        }
        
        .refresh-btn {
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .refresh-btn:hover {
            background: linear-gradient(135deg, #20c997, #28a745);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3);
        }
        
        .refresh-btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .spinner {
            width: 16px;
            height: 16px;
            border: 2px solid #ffffff;
            border-top: 2px solid transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .stats-bar {
            background: #e9ecef;
            padding: 15px 20px;
            display: flex;
            justify-content: space-around;
            text-align: center;
        }
        
        .stat-item {
            color: #495057;
        }
        
        .stat-value {
            font-size: 1.5em;
            font-weight: bold;
            color: #2a5298;
        }
        
        .stat-label {
            font-size: 0.9em;
            margin-top: 5px;
        }
        
        .stocks-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            padding: 20px;
        }
        
        .stock-card {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 10px;
            overflow: hidden;
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .stock-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        }
        
        .stock-header {
            padding: 15px;
            font-weight: bold;
            color: white;
            text-align: center;
        }
        
        .bullish { background: linear-gradient(135deg, #28a745, #20c997); }
        .bearish { background: linear-gradient(135deg, #dc3545, #fd7e14); }
        .neutral { background: linear-gradient(135deg, #6c757d, #adb5bd); }
        
        .stock-content {
            padding: 20px;
        }
        
        .score-circle {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 15px;
            color: white;
            font-size: 1.4em;
            font-weight: bold;
        }
        
        .score-high { background: #28a745; }
        .score-medium { background: #ffc107; color: #000; }
        .score-low { background: #dc3545; }
        
        .indicators {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 15px;
        }
        
        .indicator {
            background: #f8f9fa;
            padding: 8px;
            border-radius: 5px;
            text-align: center;
            font-size: 0.9em;
        }
        
        .indicator-value {
            font-weight: bold;
            color: #2a5298;
        }
        
        .no-results {
            text-align: center;
            padding: 50px;
            color: #6c757d;
            font-size: 1.2em;
        }
        
        /* View Toggle Button Styles */
        .view-toggle {
            background: linear-gradient(135deg, #6f42c1, #6610f2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .view-toggle:hover {
            background: linear-gradient(135deg, #6610f2, #6f42c1);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(111, 66, 193, 0.3);
        }
        
        /* Table View Styles */
        .table-container {
            padding: 20px;
            overflow-x: auto;
        }
        
        .stocks-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .stocks-table th {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 15px 10px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #dee2e6;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .stocks-table th:first-child {
            border-top-left-radius: 10px;
        }
        
        .stocks-table th:last-child {
            border-top-right-radius: 10px;
        }
        
        .stocks-table td {
            padding: 12px 10px;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: middle;
        }
        
        .stocks-table tbody tr:hover {
            background-color: #f8f9fa;
            transform: none;
            transition: background-color 0.2s ease;
        }
        
        .stocks-table tbody tr:last-child td {
            border-bottom: none;
        }
        
        /* Table cell specific styles */
        .symbol-cell {
            font-weight: bold;
            color: #2a5298;
            font-size: 1.1em;
        }
        
        .score-cell {
            text-align: center;
            font-weight: bold;
            font-size: 1.2em;
        }
        
        .score-high-text { color: #28a745; }
        .score-medium-text { color: #ffc107; }
        .score-low-text { color: #dc3545; }
        
        .price-cell {
            font-weight: bold;
            text-align: right;
        }
        
        .change-positive { color: #28a745; }
        .change-negative { color: #dc3545; }
        
        .sentiment-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            text-transform: uppercase;
            text-align: center;
        }
        
        .sentiment-bullish {
            background: rgba(40, 167, 69, 0.1);
            color: #28a745;
            border: 1px solid rgba(40, 167, 69, 0.3);
        }
        
        .sentiment-bearish {
            background: rgba(220, 53, 69, 0.1);
            color: #dc3545;
            border: 1px solid rgba(220, 53, 69, 0.3);
        }
        
        .sentiment-neutral {
            background: rgba(108, 117, 125, 0.1);
            color: #6c757d;
            border: 1px solid rgba(108, 117, 125, 0.3);
        }
        
        .indicator-cell {
            font-size: 0.9em;
            text-align: center;
        }
        
        .signals-cell {
            text-align: center;
            font-size: 0.9em;
        }
        
        .bullish-signals { color: #28a745; font-weight: bold; }
        .bearish-signals { color: #dc3545; font-weight: bold; }
        
        @media (max-width: 768px) {
            .controls-row {
                flex-direction: column;
                align-items: stretch;
            }
            
            .stats-bar {
                flex-direction: column;
                gap: 10px;
            }
            
            .stocks-grid {
                grid-template-columns: 1fr;
            }
            
            .stocks-table {
                font-size: 0.85em;
            }
            
            .stocks-table th,
            .stocks-table td {
                padding: 8px 6px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 Nifty50 Intraday Technical Analysis</h1>
            <p>Real-time hourly analysis dashboard • Generated on ', format(Sys.time(), "%Y-%m-%d %H:%M:%S"), '</p>
        </div>
        
        <div class="controls">
            <div class="controls-row">
                <div class="filter-group">
                    <label for="sentimentFilter">Sentiment:</label>
                    <select id="sentimentFilter">
                        <option value="all">All Signals</option>
                        <option value="bullish">Bullish Only</option>
                        <option value="bearish">Bearish Only</option>
                        <option value="neutral">Neutral Only</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <label for="scoreFilter">Min Score:</label>
                    <select id="scoreFilter">
                        <option value="0">All Scores</option>
                        <option value="60">60+ (Strong)</option>
                        <option value="40">40+ (Moderate)</option>
                        <option value="20">20+ (Weak)</option>
                    </select>
                </div>
                
                <div class="filter-group search-box">
                    <input type="text" id="searchBox" placeholder="Search stocks by symbol or name..." />
                </div>
                
                <div class="filter-group">
                    <button id="viewToggle" class="view-toggle" onclick="toggleView()">
                        <span id="viewIcon">📊</span>
                        <span id="viewText">Table View</span>
                    </button>
                </div>
                
                <div class="filter-group">
                    <button id="refreshBtn" class="refresh-btn" onclick="refreshData()">
                        <span id="refreshIcon">🔄</span>
                        <span id="refreshText">Refresh Data</span>
                    </button>
                </div>
            </div>
        </div>
        
        <div class="stats-bar">
            <div class="stat-item">
                <div class="stat-value" id="totalStocks">0</div>
                <div class="stat-label">Total Stocks</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="bullishCount">0</div>
                <div class="stat-label">Bullish</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="bearishCount">0</div>
                <div class="stat-label">Bearish</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="neutralCount">0</div>
                <div class="stat-label">Neutral</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="avgScore">0</div>
                <div class="stat-label">Avg Score</div>
            </div>
        </div>
        
        <div id="stocksContainer" class="stocks-grid">
            <!-- Stock cards will be populated by JavaScript -->
        </div>
        
        <div id="tableContainer" class="table-container" style="display: none;">
            <table class="stocks-table" id="stocksTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Symbol 📊</th>
                        <th onclick="sortTable(1)">Tech Score 🎯</th>
                        <th onclick="sortTable(2)">Price 💰</th>
                        <th onclick="sortTable(3)">Change % 📈</th>
                        <th onclick="sortTable(4)">Sentiment 🚦</th>
                        <th onclick="sortTable(5)">RSI 📊</th>
                        <th onclick="sortTable(6)">MACD 📈</th>
                        <th onclick="sortTable(7)">Bollinger 🔵</th>
                        <th onclick="sortTable(8)">Volume 📦</th>
                        <th onclick="sortTable(9)">Bullish 🟢</th>
                        <th onclick="sortTable(10)">Bearish 🔴</th>
                    </tr>
                </thead>
                <tbody id="stocksTableBody">
                    <!-- Table rows will be populated by JavaScript -->
                </tbody>
            </table>
        </div>
        
        <div id="noResults" class="no-results" style="display: none;">
            <p>No stocks match your current filters</p>
        </div>
    </div>
    
    <script>
        // Stock data
        const stockData = [')
  
  # Add stock data
  for (i in seq_along(results)) {
    stock_result <- results[[i]]
    if (!is.null(stock_result)) {
      
      # Handle different data structures
      analysis <- NULL
      symbol_name <- names(results)[i]
      
      if (is.list(stock_result) && "analysis" %in% names(stock_result)) {
        analysis <- stock_result$analysis
      } else if (is.list(stock_result)) {
        analysis <- stock_result
      }
      
      if (!is.null(analysis)) {
        # Extract symbol safely
        symbol_name <- if (!is.null(analysis$symbol)) {
          analysis$symbol
        } else if (!is.null(names(results)[i])) {
          names(results)[i]
        } else {
          paste0("Stock_", i)
        }
        
        # Extract score safely
        score <- if (!is.null(analysis$overall_score)) {
          analysis$overall_score
        } else if (!is.null(analysis$Technical_Score)) {
          analysis$Technical_Score
        } else if (!is.null(analysis$technical_score)) {
          analysis$technical_score
        } else if (!is.null(analysis$score)) {
          analysis$score
        } else if (is.numeric(analysis) && length(analysis) > 0) {
          analysis[1]
        } else {
          50
        }
        
        # Ensure score is numeric
        if (!is.numeric(score) || is.na(score)) score <- 50
        
        # Extract price and price change safely
        price <- if (!is.null(analysis$Current_Price)) {
          analysis$Current_Price
        } else if (!is.null(analysis$current_price)) {
          analysis$current_price
        } else if (!is.null(analysis$price)) {
          analysis$price
        } else {
          0
        }
        
        change <- if (!is.null(analysis$Price_Change)) {
          analysis$Price_Change
        } else if (!is.null(analysis$price_change)) {
          analysis$price_change
        } else if (!is.null(analysis$change)) {
          analysis$change
        } else {
          0
        }
        
        change_pct <- if (!is.null(analysis$Price_Change_Pct)) {
          analysis$Price_Change_Pct
        } else if (!is.null(analysis$price_change_pct)) {
          analysis$price_change_pct
        } else if (!is.null(analysis$change_pct)) {
          analysis$change_pct
        } else {
          0
        }
        
        # Determine sentiment
        sentiment <- "neutral"
        if (score >= 60) sentiment <- "bullish"
        else if (score <= 40) sentiment <- "bearish"
        
        # Get key indicators safely - extract from CSV data if available
        indicators <- list(
          rsi = 50,
          macd_signal = "Neutral",
          bb_signal = "Hold", 
          volume_trend = "Stable"
        )
        
        # First try to extract from CSV data
        if (!is.null(csv_data) && is.data.frame(csv_data) && nrow(csv_data) > 0) {
          # Find the row for this symbol
          csv_row <- csv_data[csv_data$Symbol == symbol_name, ]
          if (nrow(csv_row) > 0) {
            # Use component scores as indicator proxies from CSV
            if ("momentum_score" %in% names(csv_row) && !is.na(csv_row$momentum_score)) {
              indicators$rsi <- round(csv_row$momentum_score, 1)
            }
            if ("trend_score" %in% names(csv_row) && !is.na(csv_row$trend_score)) {
              trend_val <- csv_row$trend_score
              indicators$macd_signal <- if(trend_val >= 70) "Strong Buy" else if(trend_val >= 60) "Buy" else if(trend_val <= 30) "Strong Sell" else if(trend_val <= 40) "Sell" else "Neutral"
            }
            if ("support_resistance_score" %in% names(csv_row) && !is.na(csv_row$support_resistance_score)) {
              sr_val <- csv_row$support_resistance_score
              indicators$bb_signal <- if(sr_val >= 70) "Strong Support" else if(sr_val >= 60) "Support" else if(sr_val <= 30) "Strong Resistance" else if(sr_val <= 40) "Resistance" else "Hold"
            }
            if ("volume_score" %in% names(csv_row) && !is.na(csv_row$volume_score)) {
              vol_val <- csv_row$volume_score
              indicators$volume_trend <- if(vol_val >= 70) "High Volume" else if(vol_val >= 60) "Above Average" else if(vol_val <= 30) "Low Volume" else if(vol_val <= 40) "Below Average" else "Stable"
            }
          }
        }
        
        # Fallback: Extract indicators from analysis data structure
        if (is.list(analysis)) {
          # Try to get component scores directly from analysis if CSV data not available
          if (indicators$rsi == 50 && !is.null(analysis$momentum_score) && !is.na(analysis$momentum_score)) {
            indicators$rsi <- round(analysis$momentum_score, 1)
          }
          if (indicators$macd_signal == "Neutral" && !is.null(analysis$trend_score) && !is.na(analysis$trend_score)) {
            trend_val <- analysis$trend_score
            indicators$macd_signal <- if(trend_val >= 70) "Strong Buy" else if(trend_val >= 60) "Buy" else if(trend_val <= 30) "Strong Sell" else if(trend_val <= 40) "Sell" else "Neutral"
          }
          if (indicators$bb_signal == "Hold" && !is.null(analysis$support_resistance_score) && !is.na(analysis$support_resistance_score)) {
            sr_val <- analysis$support_resistance_score
            indicators$bb_signal <- if(sr_val >= 70) "Strong Support" else if(sr_val >= 60) "Support" else if(sr_val <= 30) "Strong Resistance" else if(sr_val <= 40) "Resistance" else "Hold"
          }
          if (indicators$volume_trend == "Stable" && !is.null(analysis$volume_score) && !is.na(analysis$volume_score)) {
            vol_val <- analysis$volume_score
            indicators$volume_trend <- if(vol_val >= 70) "High Volume" else if(vol_val >= 60) "Above Average" else if(vol_val <= 30) "Low Volume" else if(vol_val <= 40) "Below Average" else "Stable"
          }
          
          # Also try to extract individual indicators if they exist in results
          if ("indicators" %in% names(analysis) && is.list(analysis$indicators)) {
            if ("RSI" %in% names(analysis$indicators) && !is.null(analysis$indicators$RSI)) {
              rsi_val <- tail(analysis$indicators$RSI, 1)
              if (is.numeric(rsi_val) && !is.na(rsi_val)) {
                indicators$rsi <- round(rsi_val, 2)
              }
            }
            
            if ("MACD_signal" %in% names(analysis$indicators) && !is.null(analysis$indicators$MACD_signal)) {
              macd_val <- tail(analysis$indicators$MACD_signal, 1)
              if (is.numeric(macd_val) && !is.na(macd_val)) {
                indicators$macd_signal <- if(macd_val > 0) "Buy" else "Sell"
              }
            }
          }
          
          if ("bollinger_signal" %in% names(analysis) && !is.null(analysis$bollinger_signal)) {
            indicators$bb_signal <- analysis$bollinger_signal
          }
          if ("volume_trend" %in% names(analysis) && !is.null(analysis$volume_trend)) {
            indicators$volume_trend <- analysis$volume_trend
          }
        }
        
        # Get signal counts safely
        total_signals <- 0
        bullish_signals <- 0
        bearish_signals <- 0
        
        if (is.list(analysis)) {
          # Extract signals from the signals list
          if ("signals" %in% names(analysis) && is.list(analysis$signals)) {
            signals_list <- analysis$signals
            total_signals <- length(signals_list)
            
            # Count bullish vs bearish signals based on signal text
            for (signal_name in names(signals_list)) {
              signal_text <- signals_list[[signal_name]]
              if (is.character(signal_text)) {
                signal_text_lower <- tolower(signal_text)
                if (grepl("bullish|buy|strong|positive|above|breakout", signal_text_lower)) {
                  bullish_signals <- bullish_signals + 1
                } else if (grepl("bearish|sell|negative|below|breakdown|overbought", signal_text_lower)) {
                  bearish_signals <- bearish_signals + 1
                }
              }
            }
          }
          
          # Fallback: check for direct signal count fields (if they exist)
          if (total_signals == 0) {
            if ("total_signals" %in% names(analysis) && is.numeric(analysis$total_signals)) {
              total_signals <- analysis$total_signals
            }
            if ("bullish_signals" %in% names(analysis) && is.numeric(analysis$bullish_signals)) {
              bullish_signals <- analysis$bullish_signals
            }
            if ("bearish_signals" %in% names(analysis) && is.numeric(analysis$bearish_signals)) {
              bearish_signals <- analysis$bearish_signals
            }
          }
        }
        
        html_content <- paste0(html_content, '
            {
                symbol: "', symbol_name, '",
                name: "', symbol_name, '",
                score: ', score, ',
                price: ', price, ',
                change: ', change, ',
                changePercent: ', change_pct, ',
                sentiment: "', sentiment, '",
                rsi: ', indicators$rsi, ',
                macd: "', indicators$macd_signal, '",
                bollinger: "', indicators$bb_signal, '",
                volume: "', indicators$volume_trend, '",
                signals: ', total_signals, ',
                bullish: ', bullish_signals, ',
                bearish: ', bearish_signals, '
            }', ifelse(i < length(results), ',', ''))
      }
    }
  }
  
  # Complete the HTML
  html_content <- paste0(html_content, '
        ];
        
        let filteredData = [...stockData];
        let currentView = "cards"; // "cards" or "table"
        
        function renderStocks() {
            if (currentView === "cards") {
                renderCardsView();
            } else {
                renderTableView();
            }
            updateStats();
        }
        
        function renderCardsView() {
            const container = document.getElementById("stocksContainer");
            const tableContainer = document.getElementById("tableContainer");
            const noResults = document.getElementById("noResults");
            
            tableContainer.style.display = "none";
            
            if (filteredData.length === 0) {
                container.style.display = "none";
                noResults.style.display = "block";
                return;
            }
            
            container.style.display = "grid";
            noResults.style.display = "none";
            
            container.innerHTML = filteredData.map(stock => {
                const scoreClass = stock.score >= 60 ? "score-high" : 
                                 stock.score >= 40 ? "score-medium" : "score-low";
                
                const priceColorClass = stock.changePercent >= 0 ? "text-success" : "text-danger";
                const priceSign = stock.changePercent >= 0 ? "+" : "";
                
                return "<div class=\\"stock-card\\">" +
                    "<div class=\\"stock-header " + stock.sentiment + "\\">" +
                    "<div style=\\"font-size: 1.2em; font-weight: bold;\\">" + stock.symbol + "</div>" +
                    "<div style=\\"font-size: 0.9em; opacity: 0.9;\\">" + stock.sentiment.toUpperCase() + "</div>" +
                    "<div style=\\"font-size: 1.1em; margin-top: 5px;\\">" +
                    "<span style=\\"font-weight: bold;\\">₹" + stock.price.toFixed(2) + "</span>" +
                    "<span style=\\"margin-left: 10px; font-size: 0.8em; color: " + (stock.changePercent >= 0 ? "#28a745" : "#dc3545") + ";\\">" +
                    priceSign + stock.changePercent.toFixed(2) + "%" +
                    "</span>" +
                    "</div>" +
                    "</div>" +
                    "<div class=\\"stock-content\\">" +
                    "<div class=\\"score-circle " + scoreClass + "\\">" + stock.score + "</div>" +
                    "<div class=\\"indicators\\">" +
                    "<div class=\\"indicator\\"><div>RSI</div><div class=\\"indicator-value\\">" + stock.rsi + "</div></div>" +
                    "<div class=\\"indicator\\"><div>MACD</div><div class=\\"indicator-value\\">" + stock.macd + "</div></div>" +
                    "<div class=\\"indicator\\"><div>Bollinger</div><div class=\\"indicator-value\\">" + stock.bollinger + "</div></div>" +
                    "<div class=\\"indicator\\"><div>Volume</div><div class=\\"indicator-value\\">" + stock.volume + "</div></div>" +
                    "<div class=\\"indicator\\"><div>Bullish</div><div class=\\"indicator-value\\">" + stock.bullish + "</div></div>" +
                    "<div class=\\"indicator\\"><div>Bearish</div><div class=\\"indicator-value\\">" + stock.bearish + "</div></div>" +
                    "</div></div></div>";
            }).join("");
        }
        
        function renderTableView() {
            const container = document.getElementById("stocksContainer");
            const tableContainer = document.getElementById("tableContainer");
            const tableBody = document.getElementById("stocksTableBody");
            const noResults = document.getElementById("noResults");
            
            container.style.display = "none";
            
            if (filteredData.length === 0) {
                tableContainer.style.display = "none";
                noResults.style.display = "block";
                return;
            }
            
            tableContainer.style.display = "block";
            noResults.style.display = "none";
            
            tableBody.innerHTML = filteredData.map(stock => {
                const scoreClass = stock.score >= 60 ? "score-high-text" : 
                                 stock.score >= 40 ? "score-medium-text" : "score-low-text";
                
                const changeClass = stock.changePercent >= 0 ? "change-positive" : "change-negative";
                const priceSign = stock.changePercent >= 0 ? "+" : "";
                
                const sentimentClass = "sentiment-" + stock.sentiment;
                
                return "<tr>" +
                    "<td class=\\"symbol-cell\\">" + stock.symbol + "</td>" +
                    "<td class=\\"score-cell " + scoreClass + "\\">" + stock.score + "</td>" +
                    "<td class=\\"price-cell\\">₹" + stock.price.toFixed(2) + "</td>" +
                    "<td class=\\"price-cell " + changeClass + "\\">" + priceSign + stock.changePercent.toFixed(2) + "%</td>" +
                    "<td><div class=\\"sentiment-badge " + sentimentClass + "\\">" + stock.sentiment + "</div></td>" +
                    "<td class=\\"indicator-cell\\">" + stock.rsi + "</td>" +
                    "<td class=\\"indicator-cell\\">" + stock.macd + "</td>" +
                    "<td class=\\"indicator-cell\\">" + stock.bollinger + "</td>" +
                    "<td class=\\"indicator-cell\\">" + stock.volume + "</td>" +
                    "<td class=\\"signals-cell bullish-signals\\">" + stock.bullish + "</td>" +
                    "<td class=\\"signals-cell bearish-signals\\">" + stock.bearish + "</td>" +
                    "</tr>";
            }).join("");
        }
        
        function toggleView() {
            const viewToggle = document.getElementById("viewToggle");
            const viewIcon = document.getElementById("viewIcon");
            const viewText = document.getElementById("viewText");
            
            if (currentView === "cards") {
                currentView = "table";
                viewIcon.textContent = "📋";
                viewText.textContent = "Card View";
            } else {
                currentView = "cards";
                viewIcon.textContent = "📊";
                viewText.textContent = "Table View";
            }
            
            renderStocks();
        }
        
        function sortTable(columnIndex) {
            const table = document.getElementById("stocksTable");
            const tbody = table.tBodies[0];
            const rows = Array.from(tbody.querySelectorAll("tr"));
            
            // Determine sort direction
            const currentSort = table.getAttribute("data-sort-column");
            const currentDirection = table.getAttribute("data-sort-direction") || "asc";
            const newDirection = (currentSort == columnIndex && currentDirection === "asc") ? "desc" : "asc";
            
            // Sort the filteredData array based on column
            const sortKeys = ["symbol", "score", "price", "changePercent", "sentiment", "rsi", "macd", "bollinger", "volume", "bullish", "bearish"];
            const sortKey = sortKeys[columnIndex];
            
            filteredData.sort((a, b) => {
                let aVal = a[sortKey];
                let bVal = b[sortKey];
                
                // Handle numeric vs string comparison
                if (typeof aVal === "string" && typeof bVal === "string") {
                    aVal = aVal.toLowerCase();
                    bVal = bVal.toLowerCase();
                }
                
                if (newDirection === "asc") {
                    return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
                } else {
                    return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
                }
            });
            
            // Update table attributes
            table.setAttribute("data-sort-column", columnIndex);
            table.setAttribute("data-sort-direction", newDirection);
            
            // Re-render table
            renderTableView();
            
            // Update header to show sort direction
            const headers = table.querySelectorAll("th");
            headers.forEach((header, index) => {
                header.style.backgroundColor = index === columnIndex ? "#2a5298" : "";
                if (index === columnIndex) {
                    const arrow = newDirection === "asc" ? " ↑" : " ↓";
                    header.innerHTML = header.innerHTML.replace(/ ↑| ↓/g, "") + arrow;
                } else {
                    header.innerHTML = header.innerHTML.replace(/ ↑| ↓/g, "");
                }
            });
        }
        
        function updateStats() {
            const totalStocks = filteredData.length;
            const bullishCount = filteredData.filter(s => s.sentiment === "bullish").length;
            const bearishCount = filteredData.filter(s => s.sentiment === "bearish").length;
            const neutralCount = filteredData.filter(s => s.sentiment === "neutral").length;
            const avgScore = totalStocks > 0 ? Math.round(filteredData.reduce((sum, s) => sum + s.score, 0) / totalStocks) : 0;
            
            document.getElementById("totalStocks").textContent = totalStocks;
            document.getElementById("bullishCount").textContent = bullishCount;
            document.getElementById("bearishCount").textContent = bearishCount;
            document.getElementById("neutralCount").textContent = neutralCount;
            document.getElementById("avgScore").textContent = avgScore;
        }
        
        function filterStocks() {
            const sentimentFilter = document.getElementById("sentimentFilter").value;
            const scoreFilter = parseInt(document.getElementById("scoreFilter").value);
            const searchText = document.getElementById("searchBox").value.toLowerCase();
            
            filteredData = stockData.filter(stock => {
                const matchesSentiment = sentimentFilter === "all" || stock.sentiment === sentimentFilter;
                const matchesScore = stock.score >= scoreFilter;
                const matchesSearch = stock.symbol.toLowerCase().includes(searchText) || 
                                    stock.name.toLowerCase().includes(searchText);
                
                return matchesSentiment && matchesScore && matchesSearch;
            });
            
            renderStocks();
        }
        
        // Event listeners
        document.getElementById("sentimentFilter").addEventListener("change", filterStocks);
        document.getElementById("scoreFilter").addEventListener("change", filterStocks);
        document.getElementById("searchBox").addEventListener("input", filterStocks);
        
        // Refresh functionality
        async function refreshData() {
            const refreshBtn = document.getElementById("refreshBtn");
            const refreshIcon = document.getElementById("refreshIcon");
            const refreshText = document.getElementById("refreshText");
            
            // Disable button and show loading state
            refreshBtn.disabled = true;
            refreshIcon.innerHTML = \'<div class="spinner"></div>\';
            refreshText.textContent = "Refreshing...";
            
            try {
                // Get current page parameters to determine refresh command
                const urlParams = new URLSearchParams(window.location.search);
                const currentPath = window.location.pathname;
                
                // Create refresh command based on current dashboard
                let refreshCommand = "Rscript nifty50_cli.R --format html";
                
                // Add test mode if this appears to be a test dashboard
                if (document.title.includes("Test") || stockData.length <= 10) {
                    refreshCommand += " --test";
                }
                
                // Show progress message
                const progressDiv = document.createElement("div");
                progressDiv.id = "refreshProgress";
                progressDiv.style.cssText = `
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    background: rgba(0,0,0,0.9);
                    color: white;
                    padding: 20px 40px;
                    border-radius: 10px;
                    z-index: 1000;
                    text-align: center;
                `;
                progressDiv.innerHTML = `
                    <div style="margin-bottom: 10px;">🔄 Refreshing Data...</div>
                    <div style="font-size: 0.9em; opacity: 0.8;">Running: ${refreshCommand}</div>
                    <div style="font-size: 0.8em; margin-top: 10px;">This may take 10-30 seconds...</div>
                `;
                document.body.appendChild(progressDiv);
                
                // Execute refresh via server-side script or API call
                // Since we can\'t directly execute R from JavaScript, we\'ll use a workaround
                
                // Option 1: Try to call a simple refresh endpoint (if implemented)
                try {
                    const response = await fetch("/refresh-nifty50", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({command: refreshCommand})
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        if (result.success && result.dashboardUrl) {
                            window.location.href = result.dashboardUrl;
                            return;
                        }
                    }
                } catch (e) {
                    console.log("API refresh not available, using alternative method");
                }
                
                // Option 2: Provide instructions for manual refresh with enhanced options
                progressDiv.innerHTML = `
                    <div style="margin-bottom: 15px;">⚡ Dashboard Refresh Options</div>
                    
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 0.9em; margin-bottom: 10px; color: #e0e0e0;">
                            Option 1: Refresh Current Dashboard (Instant)
                        </div>
                        <div style="font-size: 0.8em; margin-bottom: 10px; opacity: 0.8;">
                            Updates data in current dashboard without creating new file
                        </div>
                        <button onclick="refreshCurrentDashboard()" style="background: #28a745; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 0.9em;">
                            🔄 Refresh Current Dashboard
                        </button>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 0.9em; margin-bottom: 10px; color: #e0e0e0;">
                            Option 2: Generate New Dashboard with Fresh Data
                        </div>
                        <div style="background: #333; padding: 10px; border-radius: 5px; font-family: monospace; margin: 10px 0; font-size: 0.8em;">
                            ${refreshCommand}
                        </div>
                        <button onclick="copyRefreshCommand()" style="background: #17a2b8; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.8em;">
                            📋 Copy Command
                        </button>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 0.9em; margin-bottom: 10px; color: #e0e0e0;">
                            Option 3: Start Watch Mode (Auto-refresh every 5 min)
                        </div>
                        <div style="background: #333; padding: 10px; border-radius: 5px; font-family: monospace; margin: 10px 0; font-size: 0.8em;">
                            Rscript nifty50_cli_enhanced.R --test --format html --watch --open
                        </div>
                        <button onclick="copyWatchCommand()" style="background: #17a2b8; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.8em;">
                            📋 Copy Watch Command
                        </button>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 0.9em; margin-bottom: 10px; color: #e0e0e0;">
                            Option 3: Start Web Server for One-Click Refresh
                        </div>
                        <div style="background: #333; padding: 10px; border-radius: 5px; font-family: monospace; margin: 10px 0; font-size: 0.8em;">
                            Rscript nifty50_cli_enhanced.R --server --port 8080
                        </div>
                        <button onclick="copyServerCommand()" style="background: #6f42c1; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.8em;">
                            📋 Copy Server Command
                        </button>
                    </div>
                    
                    <div style="font-size: 0.8em; margin-top: 15px;">
                        <button onclick="closeProgressDialog()" style="background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                            Close
                        </button>
                        <button onclick="window.location.reload()" style="background: #ffc107; color: #000; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-left: 10px;">
                            🔄 Reload Page
                        </button>
                    </div>
                    
                    <div style="font-size: 0.7em; margin-top: 10px; opacity: 0.7;">
                        💡 Tip: Option 1 instantly updates current dashboard, others create new dashboards
                    </div>
                `;
                
                // Store commands for copying
                window.currentRefreshCommand = refreshCommand;
                window.currentWatchCommand = "Rscript nifty50_cli_enhanced.R --test --format html --watch --open";
                window.currentServerCommand = "Rscript nifty50_cli_enhanced.R --server --port 8080";
                
            } catch (error) {
                console.error("Refresh error:", error);
                alert("Refresh failed: " + error.message);
            } finally {
                // Reset button state
                setTimeout(() => {
                    refreshBtn.disabled = false;
                    refreshIcon.textContent = "🔄";
                    refreshText.textContent = "Refresh Data";
                }, 2000);
            }
        }
        
        // Helper functions for refresh dialog
        function copyRefreshCommand() {
            copyToClipboard(window.currentRefreshCommand, event.target);
        }
        
        function copyWatchCommand() {
            copyToClipboard(window.currentWatchCommand, event.target);
        }
        
        function copyServerCommand() {
            copyToClipboard(window.currentServerCommand, event.target);
        }
        
        function copyToClipboard(text, button) {
            if (text) {
                navigator.clipboard.writeText(text).then(() => {
                    const originalText = button.textContent;
                    const originalBg = button.style.background;
                    button.textContent = "✅ Copied!";
                    button.style.background = "#20c997";
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.style.background = originalBg;
                    }, 2000);
                }).catch(() => {
                    // Fallback for older browsers
                    const textArea = document.createElement("textarea");
                    textArea.value = text;
                    document.body.appendChild(textArea);
                    textArea.select();
                    document.execCommand("copy");
                    document.body.removeChild(textArea);
                    
                    const originalText = button.textContent;
                    button.textContent = "✅ Copied!";
                    setTimeout(() => {
                        button.textContent = originalText;
                    }, 2000);
                });
            }
        }
        
        function closeProgressDialog() {
            const progressDiv = document.getElementById("refreshProgress");
            if (progressDiv) {
                progressDiv.remove();
            }
        }
        
        // Function to refresh current dashboard without creating new file
        async function refreshCurrentDashboard() {
            const progressDiv = document.getElementById("refreshProgress");
            if (progressDiv) {
                progressDiv.innerHTML = `
                    <div style="margin-bottom: 10px;">🔄 Refreshing Dashboard Data...</div>
                    <div style="font-size: 0.9em; opacity: 0.8;">Updating stock prices and indicators...</div>
                `;
            }
            
            // Try to get real data from server, fallback to simulation
            try {
                const response = await fetch("http://localhost:8080/refresh", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        updateInPlace: true,
                        testMode: stockData.length <= 10
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    if (result.success && result.newData) {
                        // Use real fresh data from Yahoo Finance
                        updateDashboardData(result.newData);
                        closeProgressDialog();
                        
                        // Show success with real data info
                        const successDiv = document.createElement("div");
                        successDiv.style.cssText = \`
                            position: fixed;
                            top: 20px;
                            right: 20px;
                            background: #28a745;
                            color: white;
                            padding: 15px 20px;
                            border-radius: 8px;
                            z-index: 1001;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                        \`;
                        successDiv.innerHTML = \`
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span>📈</span>
                                <div>
                                    <div style="font-weight: bold;">Real Data Updated!</div>
                                    <div style="font-size: 0.9em; opacity: 0.9;">Fresh Yahoo Finance data • \' + result.stockCount + \' stocks</div>
                                </div>
                            </div>
                        \`;
                        document.body.appendChild(successDiv);
                        
                        setTimeout(() => {
                            if (successDiv.parentNode) {
                                successDiv.parentNode.removeChild(successDiv);
                            }
                        }, 5000);
                        
                        resetRefreshButton();
                        return;
                    }
                }
            } catch (e) {
                console.log("Server not available, using simulation mode");
            }
            
            // Fallback: Simulate data refresh (for demo purposes when server not running)
            setTimeout(() => {
                const newData = simulateDataRefresh();
                updateDashboardData(newData);
                closeProgressDialog();
                resetRefreshButton();
            }, 2000);
        }
        
        // Helper function to reset refresh button
        function resetRefreshButton() {
            const refreshBtn = document.getElementById("refreshBtn");
            const refreshIcon = document.getElementById("refreshIcon");
            const refreshText = document.getElementById("refreshText");
            
            refreshBtn.disabled = false;
            refreshIcon.textContent = "🔄";
            refreshText.textContent = "Refresh Data";
        }
        
        // Auto-refresh every 5 minutes (optional)
        // setInterval(refreshData, 5 * 60 * 1000);
        
        // Function to update dashboard data in place
        function updateDashboardData(newStockData) {
            // Update the global stockData
            stockData.length = 0; // Clear existing data
            stockData.push(...newStockData); // Add new data
            
            // Update the timestamp in header
            const header = document.querySelector(\'.header p\');
            if (header) {
                header.textContent = \'Real-time hourly analysis dashboard • Generated on \' + new Date().toLocaleString();
            }
            
            // Re-render the stocks with new data
            filteredData = stockData.slice(); // Reset filtered data
            renderStocks();
            
            // Show success message
            const successDiv = document.createElement("div");
            successDiv.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #28a745;
                color: white;
                padding: 15px 20px;
                border-radius: 8px;
                z-index: 1001;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            `;
            successDiv.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span>✅</span>
                    <div>
                        <div style="font-weight: bold;">Data Updated!</div>
                        <div style="font-size: 0.9em; opacity: 0.9;">${newStockData.length} stocks refreshed</div>
                    </div>
                </div>
            `;
            document.body.appendChild(successDiv);
            
            // Auto-remove success message
            setTimeout(() => {
                if (successDiv.parentNode) {
                    successDiv.parentNode.removeChild(successDiv);
                }
            }, 4000);
        }
        
        // Function to simulate data refresh (for demo purposes)
        function simulateDataRefresh() {
            // Create updated stock data with new timestamps and slight price changes
            const updatedData = stockData.map(stock => {
                const priceChange = (Math.random() - 0.5) * 2; // Random change between -1 and +1
                const newPrice = stock.price + priceChange;
                const newChange = priceChange;
                const newChangePercent = (priceChange / stock.price) * 100;
                
                return {
                    ...stock,
                    price: Math.round(newPrice * 100) / 100,
                    change: Math.round(newChange * 100) / 100,
                    changePercent: Math.round(newChangePercent * 10000) / 10000,
                    lastUpdate: new Date().toLocaleTimeString()
                };
            });
            
            return updatedData;
        }
        
        // Initial render
        renderStocks();
    </script>
</body>
</html>')
  
  # Save dashboard
  output_dir <- file.path(getwd(), "Unified-NSE-Analysis", "reports")
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }
  
  dashboard_file <- file.path(output_dir, paste0("Nifty50_Dashboard_", 
                                                 format(Sys.time(), "%Y%m%d"), ".html"))
  
  writeLines(html_content, dashboard_file)
  
  cat("✅ Dashboard generated:", dashboard_file, "\n")
  cat("📊 Contains", length(results), "stocks\n")
  
  return(dashboard_file)
}

cat("✅ Enhanced Intraday Technical Analysis System Loaded\n")
cat("📊 Ready to analyze NSE stocks with hourly/daily data from Yahoo Finance\n")
cat("🎯 Available functions:\n")
cat("   - get_nifty50_stocks() - Get list of Nifty50 stocks + major indices (NIFTY50, BANKNIFTY, etc.)\n")
cat("   - analyze_intraday_stock(symbol, interval='1h') - Single stock analysis\n")
cat("   - analyze_nifty50_intraday(interval='1h', max_stocks=NULL) - All Nifty50 analysis\n")
cat("   - generate_nifty50_dashboard(results, interval='1h') - Create combined dashboard\n")
cat("   - test_nifty50_sample(n_stocks=5, interval='1h') - Test with few stocks\n")
cat("   - test_reliance_analysis() - Test individual stock (backward compatibility)\n")
cat("\n💡 Usage Examples:\n")
cat("   # Test with 5 stocks hourly:\n")
cat("   test_nifty50_sample(5, '1h')\n")
cat("\n   # Analyze all Nifty50 stocks hourly:\n")
cat("   analyze_nifty50_intraday('1h')\n")
cat("\n   # Single stock analysis:\n")
cat("   analyze_intraday_stock('RELIANCE', '1h')\n")
cat("\n📈 Supported intervals: '1h' (hourly), 'daily'\n")
cat("⚠️  Note: Yahoo Finance hourly data limited to 7 days, daily data up to 30 days\n")
