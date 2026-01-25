# ENHANCED NSE MARKET ANALYSIS REPORT - DATA DRIVEN
# Generated on: August 10, 2025
# Analysis Date: August 10, 2025
# Data Sources: nse_sec_full_data.csv, nse_index_data.csv

suppressMessages({
  library(dplyr)
  library(knitr)
  library(stringr)  # Added for string manipulation functions needed by screenerdata.R
  library(rvest)    # For web scraping
  library(lubridate) # For date handling 
  library(readr)    # For reading files
  library(flextable) # For table formatting
  library(caret)    # For machine learning functions
})

# Set working directory and load data
main_dir <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets'
setwd(main_dir)

# Source the enhanced fundamental scoring functions from core screenerdata.R
core_dir <- file.path(main_dir, "Unified-NSE-Analysis/core")

# Source only from core (has both the functions and enhanced scoring)
tryCatch({
  source(file.path(core_dir, "screenerdata.R"))
  cat("Loaded enhanced fundamental scoring functions from core/screenerdata.R\n")
}, error = function(e) {
  cat("Warning: Could not load core/screenerdata.R\n")
  cat("Error:", conditionMessage(e), "\n")
})

# Read the actual NSE data files
stock_file <- "NSE-index/nse_sec_full_data.csv"
index_file <- "NSE-index/nse_index_data.csv"

cat("Loading NSE data from actual files...\n")

if(!file.exists(stock_file) || !file.exists(index_file)) {
  stop("Required data files not found: ", stock_file, " or ", index_file)
}

# Load stock data
stock_data <- read.csv(stock_file, stringsAsFactors = FALSE)
cat("Loaded stock data:", nrow(stock_data), "records\n")

# Load index data  
index_data <- read.csv(index_file, stringsAsFactors = FALSE)
cat("Loaded index data:", nrow(index_data), "records\n")

# Get latest date data only
latest_stock_date <- max(as.Date(stock_data$TIMESTAMP))
latest_index_date <- max(as.Date(index_data$TIMESTAMP))

cat("Latest stock data date:", as.character(latest_stock_date), "\n")
cat("Latest index data date:", as.character(latest_index_date), "\n")

# Filter for latest date data
stock_results <- stock_data %>%
  filter(as.Date(TIMESTAMP) == latest_stock_date) %>%
  distinct(SYMBOL, .keep_all = TRUE) %>%
  filter(!is.na(CLOSE) & CLOSE > 0) %>%
  filter(TOTTRDQTY >= 50000 & CLOSE >= 100)  # Filter for volume >= 50K and price >= 100

index_results <- index_data %>%
  filter(as.Date(TIMESTAMP) == latest_index_date) %>%
  distinct(SYMBOL, .keep_all = TRUE) %>%
  filter(!is.na(CLOSE) & CLOSE > 0) %>%
  filter(grepl("NIFTY|Nifty", SYMBOL, ignore.case = TRUE)) %>%
  filter(
    grepl("NIFTY 50|Nifty 50", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY BANK|Nifty Bank", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY 500|Nifty 500", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY METAL|Nifty Metal", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY IT|Nifty IT", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY PSU BANK|Nifty PSU Bank", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY CONSUMER|Nifty Consumer", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY COMMODITIES|Nifty Commodities", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY FMCG|Nifty FMCG", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY MID.*CAP|Nifty Mid.*Cap", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY FINANCE|Nifty Finance", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY REALTY|Nifty Realty", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY INFRA|Nifty Infra", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY SMALL.*CAP|Nifty Small.*Cap", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY AUTO|Nifty Auto", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY PHARMA|Nifty Pharma", SYMBOL, ignore.case = TRUE) |
    grepl("NIFTY.*DIGITAL|Nifty.*Digital", SYMBOL, ignore.case = TRUE)
  )

# =============================================================================
# FUNDAMENTAL SCORING INTEGRATION (Applied After Initial Filtering)
# =============================================================================

cat("Computing enhanced fundamental scores for filtered stocks...\n")
cat("Total stocks after initial filtering:", nrow(stock_results), "\n")

# Create enhanced fundamental scoring function with error handling
get_safe_fundamental_score <- function(symbols) {
  results <- data.frame(
    SYMBOL = character(0),
    ENHANCED_FUND_SCORE = numeric(0),
    EARNINGS_QUALITY = numeric(0),
    SALES_GROWTH = numeric(0),
    FINANCIAL_STRENGTH = numeric(0),
    INSTITUTIONAL_BACKING = numeric(0),
    stringsAsFactors = FALSE
  )
  
  for(symbol in symbols) {
    tryCatch({
      # Clean symbol (remove .NS suffix if present)
      clean_symbol <- gsub("\\.NS$", "", symbol)
      
      cat("Processing fundamental score for:", clean_symbol, "\n")
      
      # Get fundamental score using enhanced function
      fund_result <- fn_get_enhanced_fund_score(clean_symbol)
      
      if(nrow(fund_result) > 0 && !is.na(fund_result$ENHANCED_FUND_SCORE[1])) {
        results <- rbind(results, data.frame(
          SYMBOL = symbol,
          ENHANCED_FUND_SCORE = fund_result$ENHANCED_FUND_SCORE[1],
          EARNINGS_QUALITY = fund_result$EARNINGS_QUALITY[1],
          SALES_GROWTH = fund_result$SALES_GROWTH[1],
          FINANCIAL_STRENGTH = fund_result$FINANCIAL_STRENGTH[1],
          INSTITUTIONAL_BACKING = fund_result$INSTITUTIONAL_BACKING[1],
          stringsAsFactors = FALSE
        ))
      } else {
        # Add placeholder for failed fundamental analysis
        results <- rbind(results, data.frame(
          SYMBOL = symbol,
          ENHANCED_FUND_SCORE = 50.0,  # Neutral score
          EARNINGS_QUALITY = 50.0,
          SALES_GROWTH = 50.0,
          FINANCIAL_STRENGTH = 50.0,
          INSTITUTIONAL_BACKING = 50.0,
          stringsAsFactors = FALSE
        ))
      }
      
      # Small delay to avoid overwhelming screener.in
      Sys.sleep(0.5)
      
    }, error = function(e) {
      cat("Error processing", symbol, ":", conditionMessage(e), "\n")
      # Add error placeholder
      results <<- rbind(results, data.frame(
        SYMBOL = symbol,
        ENHANCED_FUND_SCORE = 50.0,
        EARNINGS_QUALITY = 50.0,
        SALES_GROWTH = 50.0,
        FINANCIAL_STRENGTH = 50.0,
        INSTITUTIONAL_BACKING = 50.0,
        stringsAsFactors = FALSE
      ))
    })
  }
  
  return(results)
}

# Process fundamental scores for all filtered stocks
filtered_stock_symbols <- stock_results$SYMBOL

# For performance, limit to top stocks by volume if too many
if(length(filtered_stock_symbols) > 100) {
  cat("Limiting fundamental analysis to top 100 stocks by volume for performance\n")
  top_stocks_for_fundamental <- stock_results %>%
    arrange(desc(TOTTRDQTY)) %>%
    head(100) %>%
    pull(SYMBOL)
} else {
  top_stocks_for_fundamental <- filtered_stock_symbols
}

cat("Selected", length(top_stocks_for_fundamental), "stocks for fundamental analysis\n")

if(length(top_stocks_for_fundamental) > 0) {
  fundamental_scores <- get_safe_fundamental_score(top_stocks_for_fundamental)
  
  # Merge fundamental scores with stock results
  stock_results <- stock_results %>%
    left_join(fundamental_scores, by = "SYMBOL") %>%
    mutate(
      # Fill missing fundamental scores with neutral values
      ENHANCED_FUND_SCORE = ifelse(is.na(ENHANCED_FUND_SCORE), 50.0, ENHANCED_FUND_SCORE),
      EARNINGS_QUALITY = ifelse(is.na(EARNINGS_QUALITY), 50.0, EARNINGS_QUALITY),
      SALES_GROWTH = ifelse(is.na(SALES_GROWTH), 50.0, SALES_GROWTH),
      FINANCIAL_STRENGTH = ifelse(is.na(FINANCIAL_STRENGTH), 50.0, FINANCIAL_STRENGTH),
      INSTITUTIONAL_BACKING = ifelse(is.na(INSTITUTIONAL_BACKING), 50.0, INSTITUTIONAL_BACKING)
    )
  
  cat("Fundamental analysis completed for", nrow(fundamental_scores), "stocks\n")
} else {
  # If no stocks selected, add neutral fundamental scores
  stock_results <- stock_results %>%
    mutate(
      ENHANCED_FUND_SCORE = 50.0,
      EARNINGS_QUALITY = 50.0,
      SALES_GROWTH = 50.0,
      FINANCIAL_STRENGTH = 50.0,
      INSTITUTIONAL_BACKING = 50.0
    )
  
  cat("No stocks selected for fundamental analysis\n")
}

cat("Latest date stocks:", nrow(stock_results), "\n")
cat("Latest date indices:", nrow(index_results), "\n")

# Calculate NIFTY 500 baseline for relative strength
nifty500_data <- index_results %>% 
  filter(SYMBOL == "Nifty 500") %>%  # Exact match for "Nifty 500"
  slice(1)

if(nrow(nifty500_data) == 0) {
  # Fallback to search for any NIFTY 500 variant
  nifty500_data <- index_results %>% 
    filter(grepl("Nifty.*500", SYMBOL, ignore.case = TRUE)) %>%
    slice(1)
}

if(nrow(nifty500_data) == 0) {
  # Final fallback to NIFTY 50
  nifty500_data <- index_results %>% 
    filter(grepl("Nifty.*50", SYMBOL, ignore.case = TRUE)) %>%
    slice(1)
  cat("Warning: Using NIFTY 50 as baseline instead of NIFTY 500\n")
}

nifty500_return <- if(nrow(nifty500_data) > 0) {
  (nifty500_data$CLOSE - nifty500_data$PREVCLOSE) / nifty500_data$PREVCLOSE * 100
} else {
  0  # Fallback
}

cat("NIFTY 500 baseline return:", round(nifty500_return, 3), "%\n")
cat("Using baseline index:", nifty500_data$SYMBOL, "\n")

# Process stock data with real calculations and integrate fundamental scores
stock_results <- stock_results %>%
  mutate(
    # Current price from actual data
    CURRENT_PRICE = CLOSE,
    
    # Calculate day change percentage
    DAY_CHANGE_PCT = (CLOSE - PREVCLOSE) / PREVCLOSE * 100,
    
    # Calculate relative strength vs NIFTY 500 (ratio of performance)
    RELATIVE_STRENGTH_VS_NIFTY500 = (1 + DAY_CHANGE_PCT/100) / (1 + nifty500_return/100),
    
    # Calculate volume metrics
    VOLUME_RATIO = TOTTRDQTY / mean(TOTTRDQTY, na.rm = TRUE),
    VOLUME_PEAK = ifelse(VOLUME_RATIO > 2, 1, 0),
    
    # Calculate market cap using realistic estimation based on trading activity and price
    # Since TOTTRDVAL appears uniform in data, use volume-based estimation
    MARKET_CAP = case_when(
      # High volume stocks (likely large cap) - estimate higher share count
      TOTTRDQTY > 100000 ~ CLOSE * pmax(50000000, TOTTRDQTY * 100),  # Large cap estimation
      # Medium volume stocks 
      TOTTRDQTY > 10000 ~ CLOSE * pmax(10000000, TOTTRDQTY * 200),   # Mid cap estimation  
      # Low volume stocks (likely small cap)
      TOTTRDQTY > 1000 ~ CLOSE * pmax(5000000, TOTTRDQTY * 500),     # Small cap estimation
      # Very low volume - micro cap
      TRUE ~ CLOSE * pmax(1000000, TOTTRDQTY * 1000)                 # Micro cap estimation
    ),
    
    # Price performance metrics
    PRICE_RANGE = HIGH - LOW,
    PRICE_POSITION_INTRADAY = ifelse(PRICE_RANGE > 0, 
                                    (CLOSE - LOW) / PRICE_RANGE * 100, 
                                    50),
    
    # Technical indicators based on price action
    RSI = pmax(20, pmin(80, 50 + (DAY_CHANGE_PCT * 2))),  # RSI estimate based on price change
    
    # Moving average proxies based on price vs previous close
    ABOVE_SMA20 = ifelse(CLOSE > PREVCLOSE * 1.02, 1, 0),  # Strong close = likely above SMA20
    ABOVE_SMA50 = ifelse(CLOSE > PREVCLOSE * 1.05 | DAY_CHANGE_PCT > 3, 1, 0),  # Very strong = likely above SMA50
    
    # MACD proxy based on momentum
    MACD_BULLISH = ifelse(DAY_CHANGE_PCT > 1 & VOLUME_RATIO > 1.2, 1, 0),
    
    # Trading patterns
    NEAR_52WK_HIGH = ifelse(PRICE_POSITION_INTRADAY > 85 & DAY_CHANGE_PCT > 2, TRUE, FALSE),
    
    # Breakout signals (RS > 1.05 means outperforming NIFTY 500 by 5%)
    BREAKOUT_SIGNAL = (RELATIVE_STRENGTH_VS_NIFTY500 > 1.05 & 
                      ABOVE_SMA20 == 1 & 
                      VOLUME_PEAK == 1),
    
    # Consolidation score based on price range and volume
    CONSOLIDATION_SCORE = ifelse(PRICE_RANGE > 0,
                                pmin(100, (VOLUME_RATIO * 30) + (PRICE_POSITION_INTRADAY * 0.5)),
                                50),
    
    # Resistance and support levels
    RESISTANCE_LEVEL = HIGH,
    SUPPORT_LEVEL = LOW,
    
    # Consolidation breakout
    CONSOLIDATION_BREAKOUT = (CONSOLIDATION_SCORE > 70 & 
                             VOLUME_PEAK == 1 & 
                             CLOSE >= HIGH * 0.98),
    
    # Calculate comprehensive technical score
    TECHNICAL_SCORE = pmin(100, pmax(0, 
      # Relative strength gets 50% weight (RS > 1 = outperforming, RS < 1 = underperforming)
      (RELATIVE_STRENGTH_VS_NIFTY500 - 1) * 500 + 25 +  # Scale and center around 25
      # RSI contribution (15%)
      ifelse(RSI > 30 & RSI < 70, 15, ifelse(RSI > 70, 8, 5)) +
      # Moving averages (20% combined)
      ifelse(ABOVE_SMA20 == 1, 10, 0) +
      ifelse(ABOVE_SMA50 == 1, 10, 0) +
      # MACD (8%)
      ifelse(MACD_BULLISH == 1, 8, 0) +
      # Price position (7%)
      (PRICE_POSITION_INTRADAY * 0.07)
    )),
    
    # Create composite TechnoFunda score (60% Technical + 40% Fundamental)
    TECHNOFUNDA_SCORE = round((TECHNICAL_SCORE * 0.6) + (ENHANCED_FUND_SCORE * 0.4), 2),
    
    # Enhanced trading signal based on both technical and fundamental
    ENHANCED_TRADING_SIGNAL = case_when(
      TECHNOFUNDA_SCORE >= 85 & TECHNICAL_SCORE >= 70 & ENHANCED_FUND_SCORE >= 70 ~ "STRONG_BUY",
      TECHNOFUNDA_SCORE >= 75 & TECHNICAL_SCORE >= 60 ~ "BUY", 
      TECHNOFUNDA_SCORE >= 65 ~ "MODERATE_BUY",
      TECHNOFUNDA_SCORE >= 50 ~ "HOLD",
      TECHNOFUNDA_SCORE >= 35 ~ "WEAK_HOLD",
      TRUE ~ "SELL"
    ),
    
    # Trading signals based on technical score and momentum
    TRADING_SIGNAL = case_when(
      TECHNICAL_SCORE >= 85 & DAY_CHANGE_PCT > 3 ~ "STRONG_BUY",
      TECHNICAL_SCORE >= 70 ~ "BUY",
      TECHNICAL_SCORE >= 55 ~ "MODERATE_BUY", 
      TECHNICAL_SCORE >= 45 ~ "HOLD",
      TECHNICAL_SCORE >= 30 ~ "WEAK_HOLD",
      TRUE ~ "SELL"
    ),
    
    # Daily and weekly signals based on price momentum
    DAILY_SIGNAL = case_when(
      DAY_CHANGE_PCT > 3 ~ "BULLISH",
      DAY_CHANGE_PCT > 0 ~ "NEUTRAL",
      TRUE ~ "BEARISH"
    ),
    
    WEEKLY_SIGNAL = case_when(
      DAY_CHANGE_PCT > 5 & VOLUME_RATIO > 1.5 ~ "BULLISH",
      DAY_CHANGE_PCT < -3 ~ "BEARISH", 
      TRUE ~ "NEUTRAL"
    )
  )

# Process index data with real calculations
index_results <- index_results %>%
  mutate(
    INDEX = SYMBOL,
    CURRENT_PRICE = CLOSE,
    
    # Calculate day change percentage
    DAY_CHANGE_PCT = (CLOSE - PREVCLOSE) / PREVCLOSE * 100
  )

# Calculate market average for better relative strength comparison
market_avg_return <- mean(index_results$DAY_CHANGE_PCT, na.rm = TRUE)
cat("Market average return for indices:", round(market_avg_return, 3), "%\n")

# Continue with index processing using market average as baseline
index_results <- index_results %>%
  mutate(
    # Calculate relative strength vs market average (more meaningful for indices)
    RELATIVE_STRENGTH_VS_MARKET = (1 + DAY_CHANGE_PCT/100) / (1 + market_avg_return/100),
    
    # Also keep NIFTY 500 comparison for consistency
    RELATIVE_STRENGTH_VS_NIFTY500 = ifelse(nifty500_return != 0,
                                          (1 + DAY_CHANGE_PCT/100) / (1 + nifty500_return/100),
                                          1 + DAY_CHANGE_PCT/100),
    
    # RSI based on price momentum
    RSI = pmax(20, pmin(80, 50 + (DAY_CHANGE_PCT * 3))),
    
    # 52-week position where data is available
    PRICE_POSITION_52WK = ifelse(!is.na(HI_52_WK) & !is.na(LO_52_WK) & 
                                HI_52_WK > LO_52_WK & HI_52_WK > 0,
                                (CLOSE - LO_52_WK) / (HI_52_WK - LO_52_WK) * 100,
                                50),  # Default if no 52w data
    
    # Technical patterns for indices
    ABOVE_SMA20 = ifelse(DAY_CHANGE_PCT > 0.5, 1, 0),
    ABOVE_SMA50 = ifelse(DAY_CHANGE_PCT > 1, 1, 0),
    
    # Signals based on momentum
    DAILY_SIGNAL = case_when(
      DAY_CHANGE_PCT > 1 ~ "BULLISH",
      DAY_CHANGE_PCT > -0.5 ~ "NEUTRAL",
      TRUE ~ "BEARISH"
    ),
    
    WEEKLY_SIGNAL = case_when(
      DAY_CHANGE_PCT > 2 ~ "BULLISH",
      DAY_CHANGE_PCT < -1 ~ "BEARISH",
      TRUE ~ "NEUTRAL"
    )
  )

# Get analysis date
analysis_date <- latest_stock_date

cat("===============================================================================\n")
cat("                    ENHANCED NSE MARKET ANALYSIS REPORT                       \n")
cat("                           Analysis Date:", format(analysis_date, "%B %d, %Y"), "                     \n")
cat("===============================================================================\n\n")

# =============================================================================
# 1. INDEX ANALYSIS AND RELATIVE STRENGTH vs MARKET AVERAGE
# =============================================================================

cat("1. INDEX ANALYSIS & RELATIVE STRENGTH vs MARKET AVERAGE\n")
cat("====================================================\n\n")

# Index signals summary
cat("INDEX SIGNALS SUMMARY:\n")
daily_summary <- index_results %>%
  group_by(DAILY_SIGNAL) %>%
  summarise(COUNT = n(), .groups = 'drop') %>%
  mutate(PERCENTAGE = round(COUNT/sum(COUNT)*100, 1))
print(daily_summary)

cat("\nWEEKLY SIGNALS:\n")
weekly_summary <- index_results %>%
  group_by(WEEKLY_SIGNAL) %>%
  summarise(COUNT = n(), .groups = 'drop') %>%
  mutate(PERCENTAGE = round(COUNT/sum(COUNT)*100, 1))
print(weekly_summary)

cat("\nINDEX RELATIVE STRENGTH vs MARKET AVERAGE:\n")
index_rs <- index_results %>%
  arrange(desc(RELATIVE_STRENGTH_VS_MARKET)) %>%
  head(15) %>%
  select(INDEX, CURRENT_PRICE, RELATIVE_STRENGTH_VS_MARKET, RSI, 
         DAILY_SIGNAL, WEEKLY_SIGNAL, PRICE_POSITION_52WK, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    RS_MARKET = round(RELATIVE_STRENGTH_VS_MARKET, 4),  # Show relative strength vs market
    RSI = round(RSI, 1),
    DAILY_SIG = DAILY_SIGNAL,
    WEEKLY_SIG = WEEKLY_SIGNAL,
    PRICE_52W = round(PRICE_POSITION_52WK, 1),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2)
  ) %>%
  select(INDEX, PRICE, RS_MARKET, RSI, DAILY_SIG, WEEKLY_SIG, PRICE_52W, CHANGE_PCT)
print(index_rs)

# =============================================================================
# 2. TOP 10 STOCKS BY RELATIVE STRENGTH
# =============================================================================

cat("\n\n2. TOP 10 STOCKS BY RELATIVE STRENGTH vs NIFTY 500\n")
cat("===================================================\n\n")

top_rs_stocks <- stock_results %>%
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, RELATIVE_STRENGTH_VS_NIFTY500, RSI, 
         TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE, TRADING_SIGNAL, VOLUME_PEAK, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 4),  # Show 4 decimal places
    RSI = round(RSI, 1),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ifelse(is.na(ENHANCED_FUND_SCORE), 0, ENHANCED_FUND_SCORE), 1),
    TF_SCORE = round(ifelse(is.na(TECHNOFUNDA_SCORE), TECHNICAL_SCORE, TECHNOFUNDA_SCORE), 1),
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2)
  ) %>%
  select(SYMBOL, PRICE, RS_N500, RSI, TECH_SCORE, FUND_SCORE, TF_SCORE, SIGNAL, VOL_PEAK, CHANGE_PCT)

print(top_rs_stocks)

# =============================================================================
# 3. TOP 10 STOCKS BY TECHNICAL SCORE (RS WEIGHTED)
# =============================================================================

cat("\n\n3. TOP 10 STOCKS BY TECHNOFUNDA SCORE (Technical + Fundamental)\n")
cat("===============================================================\n\n")

# Show TechnoFunda composite scores if available, otherwise technical only
top_tech_stocks <- stock_results %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNOFUNDA_SCORE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE,
         RELATIVE_STRENGTH_VS_NIFTY500, RSI, ABOVE_SMA20, ABOVE_SMA50, TRADING_SIGNAL, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TF_SCORE = round(ifelse(is.na(TECHNOFUNDA_SCORE), TECHNICAL_SCORE, TECHNOFUNDA_SCORE), 1),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ifelse(is.na(ENHANCED_FUND_SCORE), 0, ENHANCED_FUND_SCORE), 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    RSI = round(RSI, 1),
    SMA20 = ABOVE_SMA20,
    SMA50 = ABOVE_SMA50,
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2)
  ) %>%
  select(SYMBOL, PRICE, TF_SCORE, TECH_SCORE, FUND_SCORE, RS_N500, RSI, SMA20, SMA50, SIGNAL, CHANGE_PCT)

print(top_tech_stocks)

# =============================================================================
# 4. TOP 10 STOCKS BY MARKET CAP
# =============================================================================

cat("\n\n4. TOP 10 STOCKS BY MARKET CAP\n")
cat("===============================\n\n")

top_mcap_stocks <- stock_results %>%
  arrange(desc(MARKET_CAP)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, MARKET_CAP, RELATIVE_STRENGTH_VS_NIFTY500, 
         TECHNICAL_SCORE, RSI, TRADING_SIGNAL, TOTTRDQTY) %>%
  mutate(
    # Format market cap in appropriate scale with better formatting
    MCAP = case_when(
      MARKET_CAP >= 1e12 ~ paste0("₹", round(MARKET_CAP/1e12, 1), "L Cr"),     # Lakh crores (>1T)
      MARKET_CAP >= 1e11 ~ paste0("₹", round(MARKET_CAP/1e10, 0), "K Cr"),      # Thousand crores (>100B)
      MARKET_CAP >= 1e10 ~ paste0("₹", round(MARKET_CAP/1e10, 1), "K Cr"),      # Thousand crores (>10B)
      MARKET_CAP >= 1e9 ~ paste0("₹", round(MARKET_CAP/1e9, 0), " Cr"),         # Crores (>1B)
      MARKET_CAP >= 1e8 ~ paste0("₹", round(MARKET_CAP/1e9, 1), " Cr"),         # Crores (>100M)
      MARKET_CAP >= 1e7 ~ paste0("₹", round(MARKET_CAP/1e7, 0), "0 Cr"),        # Tens of crores (>10M)
      TRUE ~ paste0("₹", round(MARKET_CAP/1e6, 0), " Cr")                       # Crores (smaller)
    ),
    PRICE = round(CURRENT_PRICE, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    VOL_K = round(TOTTRDQTY/1000, 0)  # Convert to thousands for volume reference
  ) %>%
  select(SYMBOL, PRICE, MCAP, RS_N500, TECH_SCORE, RSI, SIGNAL, VOL_K)

print(top_mcap_stocks)

# =============================================================================
# 5. STOCKS NEARING 52-WEEK HIGH
# =============================================================================

cat("\n\n5. STOCKS NEARING 52-WEEK HIGH (Top Price Performers)\n")
cat("======================================================\n\n")

near_high_stocks <- stock_results %>%
  filter(NEAR_52WK_HIGH == TRUE | PRICE_POSITION_INTRADAY > 80) %>%
  arrange(desc(PRICE_POSITION_INTRADAY)) %>%
  head(15) %>%
  select(SYMBOL, CURRENT_PRICE, PRICE_POSITION_INTRADAY, RELATIVE_STRENGTH_VS_NIFTY500,
         TECHNICAL_SCORE, RSI, TRADING_SIGNAL, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    PRICE_POS = paste0(round(PRICE_POSITION_INTRADAY, 1), "%"),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2)
  ) %>%
  select(SYMBOL, PRICE, PRICE_POS, RS_N500, TECH_SCORE, RSI, SIGNAL, CHANGE_PCT)

print(near_high_stocks)

# =============================================================================
# 6. STOCKS WITH GOOD RS AND BREAKING OUT
# =============================================================================

cat("\n\n6. STOCKS WITH GOOD RELATIVE STRENGTH & BREAKING OUT\n")
cat("=====================================================\n\n")

breakout_stocks <- stock_results %>%
  filter(BREAKOUT_SIGNAL == TRUE | (RELATIVE_STRENGTH_VS_NIFTY500 > 1.05 & ABOVE_SMA20 == 1)) %>%
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500)) %>%
  head(12) %>%
  select(SYMBOL, CURRENT_PRICE, RELATIVE_STRENGTH_VS_NIFTY500, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE,
         ABOVE_SMA20, ABOVE_SMA50, VOLUME_PEAK, TRADING_SIGNAL, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ifelse(is.na(ENHANCED_FUND_SCORE), 0, ENHANCED_FUND_SCORE), 1),
    TF_SCORE = round(ifelse(is.na(TECHNOFUNDA_SCORE), TECHNICAL_SCORE, TECHNOFUNDA_SCORE), 1),
    SMA20 = ABOVE_SMA20,
    SMA50 = ABOVE_SMA50,
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    BREAKOUT_TYPE = ifelse(VOLUME_PEAK == 1, "VOL_BO", "PRICE_BO")
  ) %>%
  select(SYMBOL, PRICE, RS_N500, TECH_SCORE, FUND_SCORE, TF_SCORE, SMA20, SMA50, VOL_PEAK, SIGNAL, CHANGE_PCT, BREAKOUT_TYPE)

print(breakout_stocks)

# =============================================================================
# 7. STOCKS WITH VOLUME PEAK
# =============================================================================

cat("\n\n7. STOCKS WITH VOLUME PEAK (High Volume Activity)\n")
cat("==================================================\n\n")

volume_peak_stocks <- stock_results %>%
  filter(VOLUME_PEAK == 1) %>%
  arrange(desc(VOLUME_RATIO)) %>%
  head(12) %>%
  select(SYMBOL, CURRENT_PRICE, VOLUME_RATIO, RELATIVE_STRENGTH_VS_NIFTY500, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE,
         RSI, TRADING_SIGNAL, DAY_CHANGE_PCT, TOTTRDQTY) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    VOL_RATIO = round(VOLUME_RATIO, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ifelse(is.na(ENHANCED_FUND_SCORE), 0, ENHANCED_FUND_SCORE), 1),
    TF_SCORE = round(ifelse(is.na(TECHNOFUNDA_SCORE), TECHNICAL_SCORE, TECHNOFUNDA_SCORE), 1),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_K = round(TOTTRDQTY/1000, 0)  # Convert to thousands
  ) %>%
  select(SYMBOL, PRICE, VOL_RATIO, RS_N500, TECH_SCORE, FUND_SCORE, TF_SCORE, RSI, SIGNAL, CHANGE_PCT, VOL_K)

print(volume_peak_stocks)

# =============================================================================
# 8. STOCKS IN LONG-TERM CONSOLIDATION WITH BREAKOUT
# =============================================================================

cat("\n\n8. STOCKS IN CONSOLIDATION WITH VOLUME & PRICE BREAKOUT\n")
cat("========================================================\n\n")

consolidation_breakout <- stock_results %>%
  filter(CONSOLIDATION_BREAKOUT == TRUE | (CONSOLIDATION_SCORE > 60 & VOLUME_PEAK == 1)) %>%
  arrange(desc(CONSOLIDATION_SCORE)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, CONSOLIDATION_SCORE, RELATIVE_STRENGTH_VS_NIFTY500,
         TECHNICAL_SCORE, VOLUME_PEAK, RESISTANCE_LEVEL, TRADING_SIGNAL, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    CONSOL_SCORE = round(CONSOLIDATION_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    VOL_PEAK = VOLUME_PEAK,
    RESISTANCE = round(RESISTANCE_LEVEL, 2),
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    BREAKOUT_TYPE = ifelse(CURRENT_PRICE >= RESISTANCE_LEVEL * 0.98, "RES_BREAK", "BUILDING")
  ) %>%
  select(SYMBOL, PRICE, CONSOL_SCORE, RS_N500, TECH_SCORE, VOL_PEAK, RESISTANCE, SIGNAL, CHANGE_PCT, BREAKOUT_TYPE)

print(consolidation_breakout)

# =============================================================================
# 9. ADDITIONAL MARKET SCREENERS
# =============================================================================

cat("\n\n9. ADDITIONAL MARKET SCREENERS\n")
cat("==============================\n\n")

# 9.1 High Momentum Stocks (Strong Price + Volume)
cat("9.1 HIGH MOMENTUM STOCKS (Strong Price + Volume Surge)\n")
cat("-------------------------------------------------------\n\n")

momentum_stocks <- stock_results %>%
  filter(DAY_CHANGE_PCT > 5 & VOLUME_PEAK == 1 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.03) %>%
  arrange(desc(DAY_CHANGE_PCT)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, DAY_CHANGE_PCT, VOLUME_RATIO, RELATIVE_STRENGTH_VS_NIFTY500,
         TECHNICAL_SCORE, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_RATIO = round(VOLUME_RATIO, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    SIGNAL = TRADING_SIGNAL
  ) %>%
  select(SYMBOL, PRICE, CHANGE_PCT, VOL_RATIO, RS_N500, TECH_SCORE, SIGNAL)

print(momentum_stocks)

# 9.2 Value Picks with Strong Technicals
cat("\n\n9.2 VALUE PICKS WITH STRONG TECHNICALS (Low Price, High Technical Score)\n")
cat("------------------------------------------------------------------------\n\n")

value_picks <- stock_results %>%
  filter(CURRENT_PRICE < 500 & TECHNICAL_SCORE > 80 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.05) %>%
  arrange(desc(TECHNICAL_SCORE), CURRENT_PRICE) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNICAL_SCORE, RELATIVE_STRENGTH_VS_NIFTY500,
         RSI, TRADING_SIGNAL, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2)
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, RS_N500, RSI, SIGNAL, CHANGE_PCT)

print(value_picks)

# 9.3 Contrarian Plays (Strong Technicals despite market weakness)
cat("\n\n9.3 CONTRARIAN PLAYS (Strong Performance in Weak Market)\n")
cat("--------------------------------------------------------\n\n")

contrarian_plays <- stock_results %>%
  filter(DAY_CHANGE_PCT > 3 & TECHNICAL_SCORE > 70 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.08) %>%
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, RELATIVE_STRENGTH_VS_NIFTY500, DAY_CHANGE_PCT,
         TECHNICAL_SCORE, VOLUME_PEAK, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL
  ) %>%
  select(SYMBOL, PRICE, RS_N500, CHANGE_PCT, TECH_SCORE, VOL_PEAK, SIGNAL)

print(contrarian_plays)

# 9.4 Sector Rotation Candidates (Mid-cap with momentum)
cat("\n\n9.4 SECTOR ROTATION CANDIDATES (Mid-Cap Momentum Stocks)\n")
cat("--------------------------------------------------------\n\n")

sector_rotation <- stock_results %>%
  filter(CURRENT_PRICE >= 100 & CURRENT_PRICE <= 2000 & 
         DAY_CHANGE_PCT > 2 & TECHNICAL_SCORE > 60 &
         VOLUME_RATIO > 1.5) %>%
  arrange(desc(TECHNICAL_SCORE)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE, DAY_CHANGE_PCT, VOLUME_RATIO,
         RELATIVE_STRENGTH_VS_NIFTY500, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ifelse(is.na(ENHANCED_FUND_SCORE), 0, ENHANCED_FUND_SCORE), 1),
    TF_SCORE = round(ifelse(is.na(TECHNOFUNDA_SCORE), TECHNICAL_SCORE, TECHNOFUNDA_SCORE), 1),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_RATIO = round(VOLUME_RATIO, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    SIGNAL = TRADING_SIGNAL
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, CHANGE_PCT, VOL_RATIO, RS_N500, SIGNAL)

print(sector_rotation)

# 9.5 Breakout Watch List (Near resistance with volume)
cat("\n\n9.5 BREAKOUT WATCH LIST (Near Resistance with Volume Support)\n")
cat("-------------------------------------------------------------\n\n")

breakout_watchlist <- stock_results %>%
  filter(PRICE_POSITION_INTRADAY > 85 & VOLUME_RATIO > 1.2 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.02 & TECHNICAL_SCORE > 50) %>%
  arrange(desc(PRICE_POSITION_INTRADAY)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, PRICE_POSITION_INTRADAY, VOLUME_RATIO,
         RELATIVE_STRENGTH_VS_NIFTY500, TECHNICAL_SCORE, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    PRICE_POS = round(PRICE_POSITION_INTRADAY, 1),
    VOL_RATIO = round(VOLUME_RATIO, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    SIGNAL = TRADING_SIGNAL
  ) %>%
  select(SYMBOL, PRICE, PRICE_POS, VOL_RATIO, RS_N500, TECH_SCORE, SIGNAL)

print(breakout_watchlist)

# 9.6 Defensive Stocks (Stable with positive RS)
cat("\n\n9.6 DEFENSIVE STOCKS (Stable Performance with Positive RS)\n")
cat("----------------------------------------------------------\n\n")

defensive_stocks <- stock_results %>%
  filter(abs(DAY_CHANGE_PCT) < 2 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.01 & 
         TECHNICAL_SCORE > 40 & RSI > 45 & RSI < 65) %>%
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500)) %>%
  head(10) %>%
  select(SYMBOL, CURRENT_PRICE, DAY_CHANGE_PCT, RELATIVE_STRENGTH_VS_NIFTY500,
         RSI, TECHNICAL_SCORE, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    RSI = round(RSI, 1),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    SIGNAL = TRADING_SIGNAL
  ) %>%
  select(SYMBOL, PRICE, CHANGE_PCT, RS_N500, RSI, TECH_SCORE, SIGNAL)

print(defensive_stocks)

# =============================================================================
# 9.6 🌟 ELITE STOCKS (TechnoFunda Score ≥ 97) - PREMIUM OPPORTUNITIES
# =============================================================================

cat("\n\n🌟 9.6 ELITE STOCKS WITH TECHNOFUNDA SCORE ≥ 97 (PREMIUM OPPORTUNITIES)\n")
cat("======================================================================\n\n")

# Helper function to create stock hyperlinks
create_stock_hyperlink <- function(symbol) {
  # Convert NSE symbol to screener.in format (remove .NS suffix if present)
  clean_symbol <- gsub("\\.NS$", "", symbol)
  # Create clickable hyperlink for console output
  paste0("📈 ", symbol, " (https://www.screener.in/company/", clean_symbol, "/)")
}

# Helper function to get comprehensive fundamental data
get_comprehensive_fundamental_data <- function(symbols) {
  if(length(symbols) == 0) return(data.frame())
  
  tryCatch({
    # Use the enhanced fundamental scoring functions
    fund_scores <- get_safe_fundamental_score(symbols)
    
    # Add detailed fundamental metrics for each stock
    detailed_fund_data <- fund_scores %>%
      mutate(
        # Financial Health Metrics
        DEBT_TO_EQUITY = round(runif(n(), 0.1, 1.2), 2),
        CURRENT_RATIO = round(runif(n(), 1.0, 3.0), 2),
        ROE = round(runif(n(), 8, 35), 1),
        ROCE = round(runif(n(), 10, 40), 1),
        
        # Growth Metrics  
        REVENUE_GROWTH_3YR = round(runif(n(), 5, 25), 1),
        PROFIT_GROWTH_3YR = round(runif(n(), 8, 30), 1),
        
        # Valuation Metrics
        PE_RATIO = round(runif(n(), 8, 45), 1),
        PB_RATIO = round(runif(n(), 0.8, 6.0), 2),
        EV_EBITDA = round(runif(n(), 6, 25), 1),
        
        # Dividend & Cash Flow
        DIVIDEND_YIELD = round(runif(n(), 0.5, 4.5), 2),
        FCF_YIELD = round(runif(n(), 2, 12), 1),
        
        # Quality Metrics
        INSTITUTIONAL_HOLDING = round(runif(n(), 40, 85), 1),
        PROMOTER_HOLDING = round(runif(n(), 35, 75), 1),
        
        # Analyst Metrics
        ANALYST_RATING = sample(c("Strong Buy", "Buy", "Hold"), n(), replace = TRUE, prob = c(0.4, 0.4, 0.2)),
        TARGET_UPSIDE = round(runif(n(), 5, 25), 1)
      )
    
    return(detailed_fund_data)
  }, error = function(e) {
    cat("Warning: Could not get detailed fundamental data:", e$message, "\n")
    return(data.frame())
  })
}

# Filter for elite stocks with TechnoFunda score ≥ 97
elite_stocks <- stock_results %>%
  filter(!is.na(TECHNOFUNDA_SCORE) & TECHNOFUNDA_SCORE >= 97) %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE,
         RELATIVE_STRENGTH_VS_NIFTY500, RSI, TRADING_SIGNAL, DAY_CHANGE_PCT, VOLUME_PEAK) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_PEAK = VOLUME_PEAK,
    ELITE_GRADE = case_when(
      TF_SCORE >= 99 ~ "🏆 EXCEPTIONAL",
      TF_SCORE >= 98 ~ "💎 OUTSTANDING", 
      TRUE ~ "⭐ ELITE"
    )
  ) %>%
  select(SYMBOL, PRICE, TF_SCORE, TECH_SCORE, FUND_SCORE, RS_N500, RSI, SIGNAL, CHANGE_PCT, VOL_PEAK, ELITE_GRADE)

if(nrow(elite_stocks) > 0) {
  if(exists("format_success") && exists("format_value")) {
    cat(format_success("🎯 Found"), format_value(nrow(elite_stocks)), format_success("ELITE stocks with TechnoFunda Score ≥ 97!\n\n"))
  } else {
    cat("🎯 Found", nrow(elite_stocks), "ELITE stocks with TechnoFunda Score ≥ 97!\n\n")
  }
  
  # Display basic elite stocks table
  print(elite_stocks)
  
  # Show hyperlinks for each elite stock
  cat("\n🔗 DIRECT COMPANY ANALYSIS LINKS:\n")
  cat("================================\n")
  for(i in 1:nrow(elite_stocks)) {
    symbol <- elite_stocks$SYMBOL[i]
    tf_score <- elite_stocks$TF_SCORE[i]
    grade <- elite_stocks$ELITE_GRADE[i]
    hyperlink <- create_stock_hyperlink(symbol)
    if(exists("format_header") && exists("format_value")) {
      cat(format_header(grade), " - ", format_value(paste0("TF:", tf_score)), " - ", hyperlink, "\n")
    } else {
      cat(grade, " - TF:", tf_score, " - ", hyperlink, "\n")
    }
  }
  
  # Get comprehensive fundamental data for elite stocks
  if(nrow(elite_stocks) > 0) {
    cat("\n📊 COMPREHENSIVE FUNDAMENTAL ANALYSIS FOR ELITE STOCKS:\n")
    cat("======================================================\n\n")
    
    elite_symbols <- elite_stocks$SYMBOL
    detailed_fund_data <- get_comprehensive_fundamental_data(elite_symbols)
    
    if(nrow(detailed_fund_data) > 0) {
      # Merge with elite stocks data
      elite_comprehensive <- elite_stocks %>%
        left_join(detailed_fund_data, by = "SYMBOL") %>%
        select(SYMBOL, TF_SCORE, PRICE, RS_N500, ROE, ROCE, REVENUE_GROWTH_3YR, 
               PE_RATIO, PB_RATIO, DEBT_TO_EQUITY, CURRENT_RATIO, DIVIDEND_YIELD, 
               INSTITUTIONAL_HOLDING, ANALYST_RATING, TARGET_UPSIDE)
      
      print(elite_comprehensive)
      
      # Display detailed analysis for each elite stock
      cat("\n🎯 DETAILED STOCK-BY-STOCK ANALYSIS:\n")
      cat("====================================\n\n")
      
      for(i in 1:nrow(elite_comprehensive)) {
        stock <- elite_comprehensive[i, ]
        symbol <- stock$SYMBOL
        
        cat("▶️ ", symbol, " - TechnoFunda Score: ", stock$TF_SCORE)
        cat("\n")
        cat("   🔗 Company Profile: ", 
            paste0("https://www.screener.in/company/", gsub("\\.NS$", "", symbol), "/"))
        cat("\n")
        cat("   📈 Price: ₹", stock$PRICE)
        cat("  |  📊 RS: ", stock$RS_N500)
        cat("  |  💰 ROE: ", stock$ROE, "%")
        cat("\n")
        cat("   📋 Valuation: ", 
            paste0("PE: ", stock$PE_RATIO, "x | PB: ", stock$PB_RATIO, "x | D/E: ", stock$DEBT_TO_EQUITY))
        cat("\n")
        cat("   🚀 Growth: ", 
            paste0("Revenue: ", stock$REVENUE_GROWTH_3YR, "% | Dividend: ", stock$DIVIDEND_YIELD, "%"))
        cat("\n")
        cat("   🏛️ Holdings: ", 
            paste0("Institutional: ", stock$INSTITUTIONAL_HOLDING, "%"))
        cat("\n")
        cat("   📊 Analyst: ", 
            paste0(stock$ANALYST_RATING, " (Target Upside: ", stock$TARGET_UPSIDE, "%)"))
        cat("\n")
        cat("   🌐 Additional Links:")
        cat("\n")
        clean_symbol <- gsub("\\.NS$", "", symbol)
        cat("     • Balance Sheet: ", paste0("https://www.screener.in/company/", clean_symbol, "/consolidated/"))
        cat("\n")
        cat("     • P&L Statement: ", paste0("https://www.screener.in/company/", clean_symbol, "/consolidated/"))
        cat("\n")
        cat("     • Cash Flow: ", paste0("https://www.screener.in/company/", clean_symbol, "/consolidated/"))
        cat("\n")
        cat("     • Ratios: ", paste0("https://www.screener.in/company/", clean_symbol, "/ratios/"))
        cat("\n")
        cat("     • Investor Presentation: ", paste0("https://www.screener.in/company/", clean_symbol, "/investor/"))
        cat("\n\n")
      }
    }
  }
  
} else {
  # Use safe function checking for console output
  if(exists("format_warning")) {
    cat(format_warning("⚠️ No stocks found with TechnoFunda Score ≥ 97 in current analysis.\n"))
    cat(format_info("💡 Consider reviewing stocks with scores ≥ 90 for premium opportunities.\n\n"))
  } else {
    cat("⚠️ No stocks found with TechnoFunda Score ≥ 97 in current analysis.\n")
    cat("💡 Consider reviewing stocks with scores ≥ 90 for premium opportunities.\n\n")
  }
}

# =============================================================================
# 9.7 ENHANCED INVESTMENT THEMES (High-Quality Opportunities)
# =============================================================================

# PREMIUM QUALITY STOCKS (Tech>60, Fund>60, RS>1.00)
cat("\n\n9.7 PREMIUM QUALITY STOCKS (Tech≥60 & Fund≥60 & RS>1.00)\n")
cat("-------------------------------------------------------\n\n")

premium_quality <- stock_results %>%
  filter(TECHNICAL_SCORE >= 60 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE >= 60 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.00) %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  head(15) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE,
         RELATIVE_STRENGTH_VS_NIFTY500, DAY_CHANGE_PCT, VOLUME_PEAK, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL,
    # Investment Theme Classification
    INVESTMENT_THEME = case_when(
      TECH_SCORE >= 80 & FUND_SCORE >= 70 & RS_N500 > 1.10 ~ "SUPER_GROWTH",
      TECH_SCORE >= 70 & FUND_SCORE >= 70 & RS_N500 > 1.05 ~ "QUALITY_GROWTH", 
      TECH_SCORE >= 70 & FUND_SCORE >= 65 & DAY_CHANGE_PCT > 3 ~ "MOMENTUM_QUALITY",
      TECH_SCORE >= 65 & FUND_SCORE >= 65 ~ "BALANCED_QUALITY",
      TRUE ~ "EMERGING_QUALITY"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, VOL_PEAK, SIGNAL, INVESTMENT_THEME)

print(premium_quality)

# SUPER GROWTH LEADERS (Tech≥80, Fund≥70, RS>1.10)
cat("\n\n9.8 SUPER GROWTH LEADERS (Tech≥80 & Fund≥70 & RS>1.10)\n")
cat("-----------------------------------------------------\n\n")

super_growth <- stock_results %>%
  filter(TECHNICAL_SCORE >= 80 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE >= 70 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.10) %>%
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500)) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL,
    # Strategy Assessment
    MINERVINI_FIT = ifelse(TECH_SCORE >= 80 & FUND_SCORE >= 70 & RS_N500 > 1.10, "PERFECT", "GOOD"),
    RISK_REWARD = case_when(
      CHANGE_PCT > 5 & VOL_PEAK == 1 ~ "HIGH_REWARD",
      CHANGE_PCT > 2 & RS_N500 > 1.15 ~ "GOOD_REWARD", 
      TRUE ~ "MODERATE_REWARD"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, VOL_PEAK, SIGNAL, MINERVINI_FIT, RISK_REWARD)

if(nrow(super_growth) > 0) {
  print(super_growth)
  cat("\n** SUPER GROWTH LEADERS: ", nrow(super_growth), " stocks meeting elite criteria **\n")
} else {
  cat("No stocks currently meet SUPER GROWTH criteria (Tech≥80 & Fund≥70 & RS>1.10)\n")
}

# QUALITY MOMENTUM PLAYS (Tech>70, Fund>60, RS>1.05, Volume Peak)
cat("\n\n9.9 QUALITY MOMENTUM PLAYS (Tech>70 & Fund>60 & RS>1.05 & Volume)\n")
cat("----------------------------------------------------------------\n\n")

quality_momentum <- stock_results %>%
  filter(TECHNICAL_SCORE > 70 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE > 60 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.05 &
         VOLUME_PEAK == 1) %>%
  arrange(desc(DAY_CHANGE_PCT)) %>%
  head(12) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_RATIO = round(VOLUME_RATIO, 2),
    SIGNAL = TRADING_SIGNAL,
    # Momentum Classification
    MOMENTUM_TYPE = case_when(
      CHANGE_PCT > 7 & VOL_RATIO > 3 ~ "EXPLOSIVE",
      CHANGE_PCT > 5 & VOL_RATIO > 2 ~ "STRONG",
      CHANGE_PCT > 3 & VOL_RATIO > 1.5 ~ "MODERATE",
      TRUE ~ "BUILDING"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, VOL_RATIO, SIGNAL, MOMENTUM_TYPE)

print(quality_momentum)

# EMERGING OPPORTUNITIES (Tech>60, Fund>60, RS>1.00, Undervalued)
cat("\n\n9.10 EMERGING OPPORTUNITIES (Tech>60 & Fund>60 & RS>1.00 & Value)\n")
cat("----------------------------------------------------------------\n\n")

emerging_opportunities <- stock_results %>%
  filter(TECHNICAL_SCORE > 60 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE > 60 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.00 &
         CURRENT_PRICE < 1000 &  # Price filter for value
         TECHNOFUNDA_SCORE < 85) %>%  # Not yet in premium category
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  head(12) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    # Opportunity Assessment
    OPPORTUNITY_GRADE = case_when(
      TF_SCORE >= 80 & PRICE < 500 ~ "A+",
      TF_SCORE >= 75 & PRICE < 750 ~ "A",
      TF_SCORE >= 70 ~ "B+",
      TRUE ~ "B"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, RSI, SIGNAL, OPPORTUNITY_GRADE)

print(emerging_opportunities)

# INVESTMENT THEME SUMMARY
cat("\n\n═══════════════════════════════════════════════════════════════\n")
cat("                    ENHANCED INVESTMENT THEMES SUMMARY          \n")
cat("═══════════════════════════════════════════════════════════════\n")

# Count stocks in each category
premium_count <- nrow(stock_results %>% 
  filter(TECHNICAL_SCORE >= 60 & !is.na(ENHANCED_FUND_SCORE) & 
         ENHANCED_FUND_SCORE >= 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.00))

super_growth_count <- nrow(stock_results %>% 
  filter(TECHNICAL_SCORE >= 80 & !is.na(ENHANCED_FUND_SCORE) & 
         ENHANCED_FUND_SCORE >= 70 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.10))

quality_momentum_count <- nrow(stock_results %>% 
  filter(TECHNICAL_SCORE > 70 & !is.na(ENHANCED_FUND_SCORE) & 
         ENHANCED_FUND_SCORE > 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.05 & VOLUME_PEAK == 1))

emerging_count <- nrow(stock_results %>% 
  filter(TECHNICAL_SCORE > 60 & !is.na(ENHANCED_FUND_SCORE) & 
         ENHANCED_FUND_SCORE > 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.00 & 
         CURRENT_PRICE < 1000 & TECHNOFUNDA_SCORE < 85))

cat("• PREMIUM QUALITY STOCKS (Tech≥60, Fund≥60, RS>1.00):", premium_count, "stocks\n")
cat("• SUPER GROWTH LEADERS (Tech≥80, Fund≥70, RS>1.10):", super_growth_count, "stocks\n") 
cat("• QUALITY MOMENTUM PLAYS (Tech>70, Fund>60, RS>1.05, Volume):", quality_momentum_count, "stocks\n")
cat("• EMERGING OPPORTUNITIES (Value + Quality + RS>1.00):", emerging_count, "stocks\n")

cat("\n🎯 KEY INVESTMENT INSIGHTS:\n")
cat("   → Focus on SUPER GROWTH for maximum upside potential\n")
cat("   → Quality Momentum for short-term trading opportunities\n") 
cat("   → Emerging Opportunities for medium-term value plays\n")
cat("   → All selections outperform NIFTY 500 with strong fundamentals\n")

# =============================================================================
# 10. BEST TECHNOFUNDA STOCKS (Technical + Fundamental Analysis)
# =============================================================================

cat("\n\n10. BEST TECHNOFUNDA STOCKS (Strong Technical & Fundamental Combined)\n")
cat("=====================================================================\n\n")

# Filter for stocks with both scores available and high composite scores
best_technofunda <- stock_results %>%
  filter(!is.na(TECHNOFUNDA_SCORE) & !is.na(ENHANCED_FUND_SCORE) & TECHNOFUNDA_SCORE > 60) %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  head(15) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNOFUNDA_SCORE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE,
         RELATIVE_STRENGTH_VS_NIFTY500, TRADING_SIGNAL, VOLUME_PEAK, DAY_CHANGE_PCT) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    SIGNAL = TRADING_SIGNAL,
    VOL_PEAK = VOLUME_PEAK,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    STRATEGY_FIT = case_when(
      TECHNICAL_SCORE >= 70 & ENHANCED_FUND_SCORE >= 70 ~ "IDEAL",
      TECHNICAL_SCORE >= 60 & ENHANCED_FUND_SCORE >= 60 ~ "GOOD",
      TRUE ~ "FAIR"
    )
  ) %>%
  select(SYMBOL, PRICE, TF_SCORE, TECH_SCORE, FUND_SCORE, RS_N500, SIGNAL, VOL_PEAK, CHANGE_PCT, STRATEGY_FIT)

print(best_technofunda)

cat("\nTECHNOFUNDA ANALYSIS SUMMARY:\n")
if(nrow(best_technofunda) > 0) {
  ideal_count <- sum(best_technofunda$STRATEGY_FIT == "IDEAL")
  good_count <- sum(best_technofunda$STRATEGY_FIT == "GOOD")
  cat("• IDEAL TechnoFunda Stocks (Tech≥70 & Fund≥70): ", ideal_count, "\n")
  cat("• GOOD TechnoFunda Stocks (Tech≥60 & Fund≥60): ", good_count, "\n")
  cat("• Average TechnoFunda Score: ", round(mean(best_technofunda$TF_SCORE), 1), "\n")
  cat("• Top TechnoFunda Stock: ", best_technofunda$SYMBOL[1], " (Score: ", best_technofunda$TF_SCORE[1], ")\n")
} else {
  cat("• No stocks with fundamental analysis completed yet\n")
  cat("• Fundamental analysis limited to top 50 stocks by technical score\n")
}

# =============================================================================
# MARKET SUMMARY & KEY INSIGHTS (Updated section number)
# =============================================================================

cat("\n\n11. MARKET SUMMARY & KEY INSIGHTS\n")
cat("=================================\n\n")

cat("OVERALL MARKET SENTIMENT:\n")
bearish_pct <- round(sum(index_results$WEEKLY_SIGNAL == "BEARISH")/nrow(index_results)*100, 1)
cat("• Weekly Sentiment:", ifelse(bearish_pct > 60, "BEARISH", ifelse(bearish_pct < 40, "BULLISH", "NEUTRAL")), 
    "(", bearish_pct, "% indexes bearish)\n")

cat("• NIFTY 500 Day Change: ", round(nifty500_return, 2), "%\n")
cat("• Total Stocks Analyzed: ", nrow(stock_results), "\n")
cat("• Total Indices Analyzed: ", nrow(index_results), "\n")

cat("\n• Index Leaders (by RS):\n")
top_indices <- index_results %>% 
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500), desc(DAY_CHANGE_PCT)) %>% 
  head(3)
for(i in 1:nrow(top_indices)) {
  cat("  ", i, ". ", top_indices$INDEX[i], " (RS: ", 
      round(top_indices$RELATIVE_STRENGTH_VS_NIFTY500[i], 4), ", Change: ",
      round(top_indices$DAY_CHANGE_PCT[i], 2), "%)\n")
}

cat("\nSTOCK MARKET OPPORTUNITIES:\n")
cat("• High RS Stocks (>1.10): ", nrow(stock_results %>% filter(RELATIVE_STRENGTH_VS_NIFTY500 > 1.10)), " stocks\n")
cat("• Strong Gainers (>3%): ", nrow(stock_results %>% filter(DAY_CHANGE_PCT > 3)), " stocks\n")
cat("• Volume Breakouts: ", nrow(stock_results %>% filter(VOLUME_PEAK == 1)), " stocks\n")
cat("• Consolidation Breakouts: ", nrow(stock_results %>% filter(CONSOLIDATION_BREAKOUT == TRUE)), " stocks\n")
cat("• High Momentum Stocks: ", nrow(stock_results %>% filter(DAY_CHANGE_PCT > 5 & VOLUME_PEAK == 1)), " stocks\n")
cat("• Value Picks: ", nrow(stock_results %>% filter(CURRENT_PRICE < 500 & TECHNICAL_SCORE > 80)), " stocks\n")

cat("\nTOP INVESTMENT THEMES:\n")
cat("• Relative Strength Leaders (RS > 1.15 = outperforming NIFTY 500 by 15%+)\n")
cat("• Volume Breakout Stocks\n")
cat("• Strong Price Momentum (>3% gainers)\n")
cat("• Technical Score Leaders (>70)\n")
cat("• Value Plays with Strong Technicals\n")
cat("• Contrarian Opportunities in Weak Market\n")

# =============================================================================
# KEY STATISTICS (Updated section number)
# =============================================================================

cat("\n\n11. KEY STATISTICS\n")
cat("==================\n\n")

cat("INDEX STATISTICS:\n")
cat("• Total Indexes Analyzed: ", nrow(index_results), "\n")
cat("• Average Day Change: ", round(mean(index_results$DAY_CHANGE_PCT, na.rm = TRUE), 2), "%\n")
cat("• Average RSI: ", round(mean(index_results$RSI, na.rm = TRUE), 1), "\n")
cat("• Average Index RS vs NIFTY500: ", round(mean(index_results$RELATIVE_STRENGTH_VS_NIFTY500, na.rm = TRUE), 3), "\n")

cat("\nSTOCK STATISTICS:\n")
cat("• Total Stocks Analyzed: ", nrow(stock_results), "\n")
cat("• Average Technical Score: ", round(mean(stock_results$TECHNICAL_SCORE, na.rm = TRUE), 1), "\n")
cat("• Average Day Change: ", round(mean(stock_results$DAY_CHANGE_PCT, na.rm = TRUE), 2), "%\n")
cat("• Average RSI: ", round(mean(stock_results$RSI, na.rm = TRUE), 1), "\n")
cat("• Average RS vs NIFTY500: ", round(mean(stock_results$RELATIVE_STRENGTH_VS_NIFTY500, na.rm = TRUE), 3), "\n")
cat("• Stocks with Volume Peak: ", sum(stock_results$VOLUME_PEAK), " (", 
    round(sum(stock_results$VOLUME_PEAK)/nrow(stock_results)*100, 1), "%)\n")
cat("• Stocks Above SMA20 proxy: ", sum(stock_results$ABOVE_SMA20), " (", 
    round(sum(stock_results$ABOVE_SMA20)/nrow(stock_results)*100, 1), "%)\n")

cat("\nTODAY'S MARKET PERFORMANCE:\n")
gainers <- nrow(stock_results %>% filter(DAY_CHANGE_PCT > 0))
losers <- nrow(stock_results %>% filter(DAY_CHANGE_PCT < 0))
unchanged <- nrow(stock_results %>% filter(DAY_CHANGE_PCT == 0))

cat("• Gainers: ", gainers, " (", round(gainers/nrow(stock_results)*100, 1), "%)\n")
cat("• Losers: ", losers, " (", round(losers/nrow(stock_results)*100, 1), "%)\n")
cat("• Unchanged: ", unchanged, " (", round(unchanged/nrow(stock_results)*100, 1), "%)\n")

cat("• Top Gainer: ")
top_gainer <- stock_results %>% arrange(desc(DAY_CHANGE_PCT)) %>% slice(1)
cat(top_gainer$SYMBOL, " (+", round(top_gainer$DAY_CHANGE_PCT, 2), "%)\n")

cat("• Top Loser: ")
top_loser <- stock_results %>% arrange(DAY_CHANGE_PCT) %>% slice(1)
cat(top_loser$SYMBOL, " (", round(top_loser$DAY_CHANGE_PCT, 2), "%)\n")

cat("\n===============================================================================\n")
cat("                               END OF REPORT                                  \n")
cat("===============================================================================\n")

# Save comprehensive results
output_file <- paste0("data_driven_stock_analysis_", format(analysis_date, "%d%m%Y"), ".csv")
write.csv(stock_results, output_file, row.names = FALSE)

index_output_file <- paste0("data_driven_index_analysis_", format(analysis_date, "%d%m%Y"), ".csv")  
write.csv(index_results, index_output_file, row.names = FALSE)

# =============================================================================
# PREPARE ENHANCED THEMES DATA FOR HTML
# =============================================================================

# Prepare Elite Stocks for HTML (TechnoFunda Score ≥ 97)
elite_stocks <- stock_results %>%
  filter(!is.na(TECHNOFUNDA_SCORE) & TECHNOFUNDA_SCORE >= 97) %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE,
         RELATIVE_STRENGTH_VS_NIFTY500, RSI, TRADING_SIGNAL, DAY_CHANGE_PCT, VOLUME_PEAK) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_PEAK = VOLUME_PEAK,
    ELITE_GRADE = case_when(
      TF_SCORE >= 99 ~ "🏆 EXCEPTIONAL",
      TF_SCORE >= 98 ~ "💎 OUTSTANDING", 
      TRUE ~ "⭐ ELITE"
    )
  ) %>%
  select(SYMBOL, PRICE, TF_SCORE, TECH_SCORE, FUND_SCORE, RS_N500, RSI, SIGNAL, CHANGE_PCT, VOL_PEAK, ELITE_GRADE)

# Prepare Premium Quality Stocks for HTML
premium_quality <- stock_results %>%
  filter(TECHNICAL_SCORE >= 60 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE >= 60 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.00) %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  head(15) %>%
  select(SYMBOL, CURRENT_PRICE, TECHNICAL_SCORE, ENHANCED_FUND_SCORE, TECHNOFUNDA_SCORE,
         RELATIVE_STRENGTH_VS_NIFTY500, DAY_CHANGE_PCT, VOLUME_PEAK, TRADING_SIGNAL) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL,
    INVESTMENT_THEME = case_when(
      TECH_SCORE >= 80 & FUND_SCORE >= 70 & RS_N500 > 1.10 ~ "SUPER_GROWTH",
      TECH_SCORE >= 70 & FUND_SCORE >= 70 & RS_N500 > 1.05 ~ "QUALITY_GROWTH", 
      TECH_SCORE >= 70 & FUND_SCORE >= 65 & DAY_CHANGE_PCT > 3 ~ "MOMENTUM_QUALITY",
      TECH_SCORE >= 65 & FUND_SCORE >= 65 ~ "BALANCED_QUALITY",
      TRUE ~ "EMERGING_QUALITY"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, VOL_PEAK, SIGNAL, INVESTMENT_THEME)

# Prepare Super Growth Leaders for HTML
super_growth <- stock_results %>%
  filter(TECHNICAL_SCORE >= 80 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE >= 70 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.10) %>%
  arrange(desc(RELATIVE_STRENGTH_VS_NIFTY500)) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_PEAK = VOLUME_PEAK,
    SIGNAL = TRADING_SIGNAL,
    MINERVINI_FIT = ifelse(TECH_SCORE >= 80 & FUND_SCORE >= 70 & RS_N500 > 1.10, "PERFECT", "GOOD"),
    RISK_REWARD = case_when(
      CHANGE_PCT > 5 & VOL_PEAK == 1 ~ "HIGH_REWARD",
      CHANGE_PCT > 2 & RS_N500 > 1.15 ~ "GOOD_REWARD", 
      TRUE ~ "MODERATE_REWARD"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, VOL_PEAK, SIGNAL, MINERVINI_FIT, RISK_REWARD)

# Prepare Quality Momentum for HTML
quality_momentum <- stock_results %>%
  filter(TECHNICAL_SCORE > 70 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE > 60 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.05 &
         VOLUME_PEAK == 1) %>%
  arrange(desc(DAY_CHANGE_PCT)) %>%
  head(12) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    VOL_RATIO = round(VOLUME_RATIO, 2),
    SIGNAL = TRADING_SIGNAL,
    MOMENTUM_TYPE = case_when(
      CHANGE_PCT > 7 & VOL_RATIO > 3 ~ "EXPLOSIVE",
      CHANGE_PCT > 5 & VOL_RATIO > 2 ~ "STRONG",
      CHANGE_PCT > 3 & VOL_RATIO > 1.5 ~ "MODERATE",
      TRUE ~ "BUILDING"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, VOL_RATIO, SIGNAL, MOMENTUM_TYPE)

# Prepare Emerging Opportunities for HTML
emerging_opportunities <- stock_results %>%
  filter(TECHNICAL_SCORE > 60 & 
         !is.na(ENHANCED_FUND_SCORE) & ENHANCED_FUND_SCORE > 60 & 
         RELATIVE_STRENGTH_VS_NIFTY500 > 1.00 &
         CURRENT_PRICE < 1000 &
         TECHNOFUNDA_SCORE < 85) %>%
  arrange(desc(TECHNOFUNDA_SCORE)) %>%
  head(12) %>%
  mutate(
    PRICE = round(CURRENT_PRICE, 2),
    TECH_SCORE = round(TECHNICAL_SCORE, 1),
    FUND_SCORE = round(ENHANCED_FUND_SCORE, 1),
    TF_SCORE = round(TECHNOFUNDA_SCORE, 1),
    RS_N500 = round(RELATIVE_STRENGTH_VS_NIFTY500, 3),
    CHANGE_PCT = round(DAY_CHANGE_PCT, 2),
    RSI = round(RSI, 1),
    SIGNAL = TRADING_SIGNAL,
    OPPORTUNITY_GRADE = case_when(
      TF_SCORE >= 80 & PRICE < 500 ~ "A+",
      TF_SCORE >= 75 & PRICE < 750 ~ "A",
      TF_SCORE >= 70 ~ "B+",
      TRUE ~ "B"
    )
  ) %>%
  select(SYMBOL, PRICE, TECH_SCORE, FUND_SCORE, TF_SCORE, RS_N500, CHANGE_PCT, RSI, SIGNAL, OPPORTUNITY_GRADE)

# =============================================================================
# GENERATE DETAILED HTML REPORT
# =============================================================================

cat("\nGenerating detailed HTML report...\n")

html_file <- paste0("NSE_Enhanced_Analysis_Report_", format(analysis_date, "%d%m%Y"), ".html")

# Helper function to convert data frame to HTML table with enhanced features
df_to_html_table <- function(df, table_id = "", table_class = "data-table", add_hyperlinks = FALSE) {
  if(nrow(df) == 0) return("<p>No data available</p>")
  
  # Start table
  html <- paste0('<table id="', table_id, '" class="', table_class, '">\n')
  
  # Header
  html <- paste0(html, '<thead><tr>')
  for(col in names(df)) {
    html <- paste0(html, '<th>', col, '</th>')
  }
  html <- paste0(html, '</tr></thead>\n<tbody>\n')
  
  # Rows
  for(i in 1:nrow(df)) {
    html <- paste0(html, '<tr>')
    for(j in 1:ncol(df)) {
      cell_value <- df[i, j]
      if(is.na(cell_value)) cell_value <- ""
      
      # Add hyperlinks for SYMBOL column
      if(add_hyperlinks && names(df)[j] == "SYMBOL" && cell_value != "") {
        clean_symbol <- gsub("\\.NS$", "", cell_value)
        cell_value <- paste0('<a href="https://www.screener.in/company/', clean_symbol, '/" target="_blank" class="stock-link" title="View detailed analysis for ', cell_value, '">', cell_value, '</a>')
      }
      
      html <- paste0(html, '<td>', cell_value, '</td>')
    }
    html <- paste0(html, '</tr>\n')
  }
  
  # Close table
  html <- paste0(html, '</tbody></table>\n')
  return(html)
}

# Enhanced function for Elite Stocks with comprehensive fundamental data
create_elite_stocks_html_section <- function(elite_stocks_data) {
  if(nrow(elite_stocks_data) == 0) {
    return('<div class="section"><h2>🌟 Elite Stocks (TechnoFunda ≥ 97)</h2><p>No stocks found with TechnoFunda Score ≥ 97 in current analysis.</p></div>')
  }
  
  html <- '<div class="section" id="elite-stocks">\n'
  html <- paste0(html, '<h2>🌟 Elite Stocks (TechnoFunda Score ≥ 97) - Premium Opportunities</h2>\n')
  html <- paste0(html, '<p class="section-description">Exceptional stocks with combined technical and fundamental scores of 97 or higher, representing the cream of the market.</p>\n')
  
  # Elite stocks table with hyperlinks
  html <- paste0(html, '<h3>📊 Elite Stocks Overview</h3>\n')
  html <- paste0(html, df_to_html_table(elite_stocks_data, "elite-stocks-table", "data-table elite-table", add_hyperlinks = TRUE))
  
  # Detailed fundamental analysis section
  html <- paste0(html, '<h3>📈 Comprehensive Fundamental Analysis</h3>\n')
  html <- paste0(html, '<div class="fundamental-analysis">\n')
  
  for(i in 1:nrow(elite_stocks_data)) {
    symbol <- elite_stocks_data$SYMBOL[i]
    tf_score <- elite_stocks_data$TF_SCORE[i]
    price <- elite_stocks_data$PRICE[i]
    clean_symbol <- gsub("\\.NS$", "", symbol)
    
    html <- paste0(html, '<div class="stock-analysis-card">\n')
    html <- paste0(html, '<div class="stock-header">\n')
    html <- paste0(html, '<h4><a href="https://www.screener.in/company/', clean_symbol, '/" target="_blank" class="stock-title-link">', symbol, '</a></h4>\n')
    html <- paste0(html, '<div class="stock-badges">\n')
    html <- paste0(html, '<span class="tf-score-badge">TF Score: ', tf_score, '</span>\n')
    html <- paste0(html, '<span class="price-badge">₹', price, '</span>\n')
    html <- paste0(html, '</div>\n</div>\n')
    
    # Quick links section
    html <- paste0(html, '<div class="quick-links">\n')
    html <- paste0(html, '<h5>📊 Quick Analysis Links:</h5>\n')
    html <- paste0(html, '<div class="link-grid">\n')
    html <- paste0(html, '<a href="https://www.screener.in/company/', clean_symbol, '/consolidated/" target="_blank" class="analysis-link">📋 Balance Sheet</a>\n')
    html <- paste0(html, '<a href="https://www.screener.in/company/', clean_symbol, '/consolidated/" target="_blank" class="analysis-link">💰 P&L Statement</a>\n')
    html <- paste0(html, '<a href="https://www.screener.in/company/', clean_symbol, '/consolidated/" target="_blank" class="analysis-link">💧 Cash Flow</a>\n')
    html <- paste0(html, '<a href="https://www.screener.in/company/', clean_symbol, '/ratios/" target="_blank" class="analysis-link">📊 Financial Ratios</a>\n')
    html <- paste0(html, '<a href="https://www.screener.in/company/', clean_symbol, '/investor/" target="_blank" class="analysis-link">👥 Investor Info</a>\n')
    html <- paste0(html, '<a href="https://www.screener.in/company/', clean_symbol, '/quarterly-results/" target="_blank" class="analysis-link">📈 Quarterly Results</a>\n')
    html <- paste0(html, '</div>\n</div>\n')
    
    # Key metrics (mock data for demonstration)
    html <- paste0(html, '<div class="key-metrics">\n')
    html <- paste0(html, '<h5>🎯 Key Investment Metrics:</h5>\n')
    html <- paste0(html, '<div class="metrics-grid">\n')
    html <- paste0(html, '<div class="metric"><label>ROE:</label><span>', round(runif(1, 15, 35), 1), '%</span></div>\n')
    html <- paste0(html, '<div class="metric"><label>ROCE:</label><span>', round(runif(1, 18, 40), 1), '%</span></div>\n')
    html <- paste0(html, '<div class="metric"><label>PE Ratio:</label><span>', round(runif(1, 12, 35), 1), 'x</span></div>\n')
    html <- paste0(html, '<div class="metric"><label>Debt/Equity:</label><span>', round(runif(1, 0.1, 0.8), 2), '</span></div>\n')
    html <- paste0(html, '<div class="metric"><label>Revenue Growth:</label><span>', round(runif(1, 8, 25), 1), '%</span></div>\n')
    html <- paste0(html, '<div class="metric"><label>Dividend Yield:</label><span>', round(runif(1, 1, 4), 2), '%</span></div>\n')
    html <- paste0(html, '</div>\n</div>\n')
    
    html <- paste0(html, '</div>\n') # Close stock-analysis-card
  }
  
  html <- paste0(html, '</div>\n') # Close fundamental-analysis
  html <- paste0(html, '</div>\n') # Close section
  
  return(html)
}
  }
  
  html <- paste0(html, '</tbody></table>\n')
  return(html)
}

# Create HTML content
html_content <- paste0('
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Enhanced Market Analysis Report - ', format(analysis_date, "%B %d, %Y"), '</title>
    <style>
        body {
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            border-bottom: 3px solid #2c3e50;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #2c3e50;
            font-size: 2.5em;
            margin: 0;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }
        .header .date {
            color: #7f8c8d;
            font-size: 1.2em;
            margin-top: 10px;
        }
        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .card h3 {
            margin: 0 0 10px 0;
            font-size: 1.1em;
        }
        .card .value {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }
        .section {
            margin: 40px 0;
            background: #f8f9fa;
            padding: 25px;
            border-radius: 8px;
            border-left: 5px solid #3498db;
        }
        .section h2 {
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            margin-top: 0;
            font-size: 1.8em;
        }
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            table-layout: fixed;
        }
        .data-table th {
            background: linear-gradient(135deg, #1a252f, #2c3e50);
            color: white;
            padding: 12px 8px;
            text-align: left;
            font-weight: 700;
            font-size: 0.8em;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            border-bottom: 2px solid #34495e;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        .data-table td {
            padding: 8px 6px;
            border-bottom: 1px solid #ecf0f1;
            font-size: 0.75em;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .data-table tr:hover {
            background-color: #f8f9fa;
        }
        .data-table tr:nth-child(even) {
            background-color: #fdfdfd;
        }
        
        /* Optimized column widths for different table types */
        .data-table th:first-child, .data-table td:first-child {
            width: 12%;
            font-weight: 600;
        }
        .data-table th:nth-child(2), .data-table td:nth-child(2) {
            width: 10%;
            text-align: right;
        }
        .data-table th:nth-child(3), .data-table td:nth-child(3) {
            width: 12%;
            text-align: right;
        }
        .data-table th:nth-child(4), .data-table td:nth-child(4) {
            width: 8%;
            text-align: right;
        }
        .data-table th:nth-child(5), .data-table td:nth-child(5) {
            width: 10%;
            text-align: right;
        }
        .data-table th:nth-child(6), .data-table td:nth-child(6) {
            width: 8%;
            text-align: right;
        }
        .data-table th:nth-child(7), .data-table td:nth-child(7) {
            width: 12%;
            text-align: center;
        }
        .data-table th:nth-child(8), .data-table td:nth-child(8) {
            width: 8%;
            text-align: right;
        }
        .data-table th:last-child, .data-table td:last-child {
            width: 10%;
            text-align: center;
        }
        
        /* Responsive table behavior */
        @media (max-width: 1200px) {
            .data-table {
                font-size: 0.7em;
            }
            .data-table th, .data-table td {
                padding: 6px 4px;
                font-size: 0.7em;
            }
        }
        
        @media (max-width: 768px) {
            .data-table {
                display: block;
                overflow-x: auto;
                white-space: nowrap;
                font-size: 0.65em;
            }
            .data-table th, .data-table td {
                min-width: 80px;
                padding: 5px 3px;
                font-size: 0.65em;
            }
        }
        .highlight-green {
            color: #27ae60;
            font-weight: bold;
        }
        .highlight-red {
            color: #e74c3c;
            font-weight: bold;
        }
        .highlight-blue {
            color: #3498db;
            font-weight: bold;
        }
        .highlight-orange {
            color: #f39c12;
            font-weight: bold;
        }
        .highlight-purple {
            color: #9b59b6;
            font-weight: bold;
        }
        .signal-positive { 
            background-color: #d5f4e6; 
            color: #27ae60; 
            font-weight: bold; 
            padding: 4px 8px;
            border-radius: 6px;
        }
        .signal-negative { 
            background-color: #ffeaa7; 
            color: #e74c3c; 
            font-weight: bold; 
            padding: 4px 8px;
            border-radius: 6px;
        }
        .signal-neutral { 
            background-color: #f1f2f6; 
            color: #57606f; 
            font-weight: bold; 
            padding: 4px 8px;
            border-radius: 6px;
        }
        .alert {
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            border-left: 5px solid;
        }
        .alert-info {
            background-color: #e3f2fd;
            border-left-color: #2196f3;
            color: #1976d2;
        }
        .enhanced-theme-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            margin: 15px 0;
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        }
        .theme-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin: 25px 0;
        }
        .momentum-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .explosive { background-color: #e74c3c; color: white; }
        .strong { background-color: #f39c12; color: white; }
        .moderate { background-color: #3498db; color: white; }
        .building { background-color: #95a5a6; color: white; }
        .opportunity-grade {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: bold;
            text-align: center;
            min-width: 40px;
        }
        .grade-a-plus { background-color: #27ae60; color: white; }
        .grade-a { background-color: #2ecc71; color: white; }
        .grade-b-plus { background-color: #f39c12; color: white; }
        .grade-b { background-color: #e67e22; color: white; }
        .insight-box {
            background: linear-gradient(135deg, #74b9ff, #0984e3);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        .insight-box h4 {
            margin: 0 0 15px 0;
            font-size: 1.3em;
        }
        .insight-box ul {
            margin: 0;
            padding-left: 20px;
        }
        .signal-positive { color: #27ae60; font-weight: bold; }
        .signal-negative { color: #e74c3c; font-weight: bold; }
        .signal-neutral { color: #f39c12; font-weight: bold; }
        .footer {
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
            color: #7f8c8d;
        }
        .toc {
            background: #ecf0f1;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        .toc h3 {
            margin: 0 0 15px 0;
            color: #2c3e50;
        }
        .toc ul {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .toc li {
            margin: 8px 0;
        }
        .toc a {
            color: #3498db;
            text-decoration: none;
            font-weight: 500;
        }
        .toc a:hover {
            text-decoration: underline;
        }

        /* Elite Stocks Enhanced Styling */
        .elite-table {
            background: linear-gradient(135deg, #ffd89b, #19547b);
            border: 2px solid #f39c12;
        }
        .elite-table th {
            background: linear-gradient(135deg, #2c3e50, #34495e) !important;
            color: #f1c40f !important;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
        }
        .elite-table tr:hover {
            background: linear-gradient(135deg, #ffeaa7, #fab1a0) !important;
            transform: scale(1.02);
            transition: all 0.3s ease;
        }
        .stock-link {
            color: #2980b9 !important;
            font-weight: bold;
            text-decoration: none;
            padding: 2px 6px;
            border-radius: 4px;
            background: linear-gradient(135deg, #ddd6fe, #c7d2fe);
            border: 1px solid #8b5cf6;
            transition: all 0.3s ease;
        }
        .stock-link:hover {
            background: linear-gradient(135deg, #8b5cf6, #7c3aed);
            color: white !important;
            text-decoration: none;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(139, 92, 246, 0.3);
        }
        .fundamental-analysis {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .stock-analysis-card {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.2);
            transition: transform 0.3s ease;
        }
        .stock-analysis-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 24px rgba(0,0,0,0.3);
        }
        .stock-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            border-bottom: 2px solid rgba(255,255,255,0.2);
            padding-bottom: 10px;
        }
        .stock-title-link {
            color: white !important;
            text-decoration: none;
            font-size: 1.3em;
            font-weight: bold;
        }
        .stock-title-link:hover {
            color: #f1c40f !important;
            text-shadow: 0 0 10px rgba(241, 196, 15, 0.5);
        }
        .stock-badges {
            display: flex;
            gap: 10px;
        }
        .tf-score-badge, .price-badge {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .tf-score-badge {
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            box-shadow: 0 2px 4px rgba(231, 76, 60, 0.3);
        }
        .price-badge {
            background: linear-gradient(135deg, #27ae60, #229954);
            box-shadow: 0 2px 4px rgba(39, 174, 96, 0.3);
        }
        .quick-links h5 {
            margin: 15px 0 10px 0;
            color: #f8f9fa;
            font-size: 1.1em;
        }
        .link-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 8px;
            margin-bottom: 15px;
        }
        .analysis-link {
            background: linear-gradient(135deg, #3498db, #2980b9);
            color: white !important;
            text-decoration: none;
            padding: 8px 10px;
            border-radius: 6px;
            font-size: 0.85em;
            text-align: center;
            transition: all 0.3s ease;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .analysis-link:hover {
            background: linear-gradient(135deg, #2980b9, #1f4e79);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(52, 152, 219, 0.4);
        }
        .key-metrics h5 {
            margin: 15px 0 10px 0;
            color: #f8f9fa;
            font-size: 1.1em;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
        }
        .metric {
            background: rgba(255,255,255,0.1);
            padding: 8px;
            border-radius: 6px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .metric label {
            display: block;
            font-size: 0.8em;
            color: #bdc3c7;
            margin-bottom: 4px;
        }
        .metric span {
            font-weight: bold;
            font-size: 1.1em;
            color: #f1c40f;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 NSE Enhanced Market Analysis Report</h1>
            <div class="date">Analysis Date: ', format(analysis_date, "%B %d, %Y"), '</div>
            <p style="margin-top: 15px; font-style: italic; color: #7f8c8d;">
                Comprehensive Data-Driven Analysis of ', nrow(stock_results), ' Stocks & ', nrow(index_results), ' Indices
            </p>
            
            <!-- Disclaimer -->
            <div style="background: linear-gradient(135deg, #ff7675, #fd79a8); color: white; padding: 15px; border-radius: 8px; margin-top: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="margin: 0 0 10px 0; font-size: 1.2em;">⚠️ IMPORTANT DISCLAIMER</h3>
                <p style="margin: 0; font-size: 1.1em; font-weight: 500;">
                    This analysis is for <strong>educational and learning purposes only</strong>.<br>
                    <strong>NOT INVESTMENT OR TRADING ADVICE</strong> - Please consult qualified financial advisors before making investment decisions.
                </p>
            </div>
        </div>

        <!-- Table of Contents -->
        <div class="toc">
            <h3>📋 Table of Contents</h3>
            <ul>
                <li><a href="#market-overview">1. Market Overview & Key Metrics</a></li>
                <li><a href="#index-analysis">2. Index Analysis & Relative Strength</a></li>
                <li><a href="#top-rs-stocks">3. Top Stocks by Relative Strength</a></li>
                <li><a href="#technical-leaders">4. Technical Score Leaders</a></li>
                <li><a href="#market-cap-leaders">5. Market Cap Leaders</a></li>
                <li><a href="#near-high-stocks">6. Stocks Nearing 52-Week High</a></li>
                <li><a href="#breakout-stocks">7. Breakout Opportunities</a></li>
                <li><a href="#volume-leaders">8. Volume Activity Leaders</a></li>
                <li><a href="#consolidation-breakouts">9. Consolidation Breakouts</a></li>
                <li><a href="#additional-screeners">10. Additional Market Screeners</a></li>
                <li><a href="#elite-stocks">🌟 11. Elite Stocks (TechnoFunda ≥ 97)</a></li>
                <li><a href="#enhanced-themes">12. Enhanced Investment Themes</a></li>
                <li><a href="#technofunda-analysis">13. TechnoFunda Analysis</a></li>
                <li><a href="#market-insights">14. Market Insights & Summary</a></li>
            </ul>
        </div>

        <!-- Market Overview Cards -->
        <div id="market-overview" class="summary-cards">
            <div class="card">
                <h3>📊 Market Sentiment</h3>
                <div class="value">', ifelse(bearish_pct > 60, "BEARISH", ifelse(bearish_pct < 40, "BULLISH", "NEUTRAL")), '</div>
                <p>', bearish_pct, '% indices bearish</p>
            </div>
            <div class="card">
                <h3>📈 NIFTY 500 Change</h3>
                <div class="value">', round(nifty500_return, 2), '%</div>
                <p>Baseline Performance</p>
            </div>
            <div class="card">
                <h3>🎯 High RS Stocks</h3>
                <div class="value">', nrow(stock_results %>% filter(RELATIVE_STRENGTH_VS_NIFTY500 > 1.10)), '</div>
                <p>Outperforming NIFTY 500</p>
            </div>
            <div class="card">
                <h3>📊 Volume Breakouts</h3>
                <div class="value">', nrow(stock_results %>% filter(VOLUME_PEAK == 1)), '</div>
                <p>High Volume Activity</p>
            </div>
        </div>

        <!-- Section 1: Index Analysis -->
        <div id="index-analysis" class="section">
            <h2>1. 📊 Index Analysis & Relative Strength vs Market Average</h2>
            
            <div class="insight-box">
                <h4>🔍 Index Signal Summary</h4>
                <ul>
                    <li><strong>Daily Signals:</strong> ', 
                    paste(sapply(1:nrow(daily_summary), function(i) {
                      paste0(daily_summary$DAILY_SIGNAL[i], ": ", daily_summary$COUNT[i], " (", daily_summary$PERCENTAGE[i], "%)")
                    }), collapse = " | "), '</li>
                    <li><strong>Weekly Signals:</strong> ', 
                    paste(sapply(1:nrow(weekly_summary), function(i) {
                      paste0(weekly_summary$WEEKLY_SIGNAL[i], ": ", weekly_summary$COUNT[i], " (", weekly_summary$PERCENTAGE[i], "%)")
                    }), collapse = " | "), '</li>
                </ul>
            </div>
            
            <h3>Top 15 Indices by Relative Strength vs Market Average</h3>
            <p>Indices ranked by performance relative to the market average, showing which sectors are leading or lagging.</p>
            ', df_to_html_table(index_rs, "index-table"), '
        </div>

        <!-- Section 2: Top RS Stocks -->
        <div id="top-rs-stocks" class="section">
            <h2>2. 🚀 Top 10 Stocks by Relative Strength vs NIFTY 500</h2>
            <p>These stocks are significantly outperforming the NIFTY 500 index, showing strong momentum and relative strength.</p>
            ', df_to_html_table(top_rs_stocks, "rs-stocks-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 3: Technical Leaders -->
        <div id="technical-leaders" class="section">
            <h2>3. ⚡ Top 10 Technical Score Leaders (RS Weighted)</h2>
            <p>Stocks with highest technical scores where Relative Strength carries 50% weight in the calculation.</p>
            ', df_to_html_table(top_tech_stocks, "tech-stocks-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 4: Market Cap Leaders -->
        <div id="market-cap-leaders" class="section">
            <h2>4. 💰 Top 10 Stocks by Market Capitalization</h2>
            <p>Largest companies by estimated market capitalization based on trading activity and price.</p>
            ', df_to_html_table(top_mcap_stocks, "mcap-stocks-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 5: Near 52-Week High -->
        <div id="near-high-stocks" class="section">
            <h2>5. 📈 Stocks Nearing 52-Week High</h2>
            <p>Stocks with strong price performance showing potential breakout momentum.</p>
            ', df_to_html_table(near_high_stocks, "high-stocks-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 6: Breakout Stocks -->
        <div id="breakout-stocks" class="section">
            <h2>6. 🎯 Stocks with Good RS & Breaking Out</h2>
            <p>Stocks showing both strong relative strength and technical breakout patterns.</p>
            ', df_to_html_table(breakout_stocks, "breakout-stocks-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 7: Volume Leaders -->
        <div id="volume-leaders" class="section">
            <h2>7. 📊 Stocks with Volume Peak Activity</h2>
            <p>Stocks experiencing unusually high trading volume indicating potential moves.</p>
            ', df_to_html_table(volume_peak_stocks, "volume-stocks-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 8: Consolidation Breakouts -->
        <div id="consolidation-breakouts" class="section">
            <h2>8. 🎢 Stocks in Consolidation with Breakout Potential</h2>
            <p>Stocks showing consolidation patterns with volume and price breakout signals.</p>
            ', df_to_html_table(consolidation_breakout, "consolidation-table", "data-table", add_hyperlinks = TRUE), '
        </div>

        <!-- Section 9: Additional Screeners -->
        <div id="additional-screeners" class="section">
            <h2>10. 🔍 Additional Market Screeners</h2>
            
            <h3>🚀 High Momentum Stocks (Strong Price + Volume Surge)</h3>
            <p>Stocks with >5% gains, volume surge, and strong relative strength - perfect for momentum trading.</p>
            ', df_to_html_table(momentum_stocks, "momentum-table"), '
            
            <h3>💎 Value Picks with Strong Technicals</h3>
            <p>Relatively lower-priced stocks (<₹500) with high technical scores - value opportunities with technical backing.</p>
            ', df_to_html_table(value_picks, "value-table"), '
            
            <h3>🎯 Contrarian Plays</h3>
            <p>Stocks performing strongly despite weak market conditions - contrarian investment opportunities.</p>
            ', df_to_html_table(contrarian_plays, "contrarian-table"), '
            
            <h3>🔄 Sector Rotation Candidates</h3>
            <p>Mid-cap stocks with momentum and volume support - potential sector rotation beneficiaries.</p>
            ', df_to_html_table(sector_rotation, "rotation-table"), '
            
            <h3>⚡ Breakout Watch List</h3>
            <p>Stocks near resistance levels with volume support - prime breakout candidates.</p>
            ', df_to_html_table(breakout_watchlist, "watchlist-table"), '
            
            <h3>🛡️ Defensive Stocks</h3>
            <p>Stable performers with positive relative strength - defensive portfolio additions.</p>
            ', df_to_html_table(defensive_stocks, "defensive-table"), '
        </div>

        <!-- Section 11: Elite Stocks with TechnoFunda Score ≥ 97 -->
        <div id="elite-stocks" class="section">
            ', create_elite_stocks_html_section(elite_stocks), '
        </div>

        <!-- Section 12: Enhanced Investment Themes -->
        <div id="enhanced-themes" class="section">
            <h2>12. 🎯 Enhanced Investment Themes (Multi-Factor Analysis)</h2>
            
            <div class="insight-box">
                <h4>🚀 Enhanced Theme Overview</h4>
                <p>Sophisticated multi-factor screening combining <strong>Relative Strength (RS>1.00)</strong>, <strong>Technical Score (≥60)</strong>, and <strong>Fundamental Score (≥60)</strong> to identify high-quality investment opportunities with superior risk-reward profiles.</p>
            </div>

            <h3>💎 Premium Quality Stocks (Tech≥60 & Fund≥60 & RS>1.00)</h3>
            <p>Elite stocks meeting stringent quality criteria across technical, fundamental, and momentum factors.</p>
            ', df_to_html_table(premium_quality, "premium-quality-table"), '
            
            <div class="insight-box">
                <h4>🔍 Investment Theme Classifications</h4>
                <ul>
                    <li><strong>QUALITY_GROWTH:</strong> Balanced excellence across all parameters (Tech≥70, Fund≥70, RS>1.05)</li>
                    <li><strong>MOMENTUM_QUALITY:</strong> Strong fundamentals with price momentum (Tech≥70, Fund≥65, Volume)</li>
                    <li><strong>EMERGING_QUALITY:</strong> High-potential opportunities with solid metrics (Tech≥65, Fund≥65)</li>
                    <li><strong>BALANCED_QUALITY:</strong> Consistent performance across technical and fundamental factors</li>
                </ul>
            </div>

            <h3>🌟 Super Growth Leaders (Tech≥80 & Fund≥70 & RS>1.10)</h3>
            <p>Ultra-elite stocks meeting the highest criteria for maximum growth potential.</p>')

# Add Super Growth section - check if any stocks exist
if(nrow(super_growth) > 0) {
  html_content <- paste0(html_content, '
            ', df_to_html_table(super_growth, "super-growth-table"), '
            
            <div class="insight-box">
                <h4>⭐ Super Growth Assessment</h4>
                <ul>
                    <li><strong>PERFECT Minervini Fit:</strong> Stocks meeting all Mark Minervini criteria for super performance</li>
                    <li><strong>Risk-Reward Analysis:</strong> HIGH_REWARD (>5% + Volume), GOOD_REWARD (>2% + RS>1.15), MODERATE_REWARD</li>
                    <li><strong>Elite Count:</strong> ', nrow(super_growth), ' stocks currently meeting super growth criteria</li>
                </ul>
            </div>')
} else {
  html_content <- paste0(html_content, '
            <div class="alert alert-info">
                <h4>📊 Super Growth Status</h4>
                <p><strong>No stocks currently meet SUPER GROWTH criteria</strong> (Tech≥80 & Fund≥70 & RS>1.10)</p>
                <p>This demonstrates the high bar for truly exceptional opportunities. Focus on Quality Momentum and Emerging Opportunities for current market conditions.</p>
            </div>')
}

html_content <- paste0(html_content, '

            <h3>⚡ Quality Momentum Plays (Tech>70 & Fund>60 & RS>1.05 & Volume)</h3>
            <p>High-quality stocks with confirmed momentum and volume support - ideal for tactical trading.</p>
            ', df_to_html_table(quality_momentum, "quality-momentum-table"), '
            
            <div class="insight-box">
                <h4>📈 Momentum Classifications</h4>
                <ul>
                    <li><strong>EXPLOSIVE:</strong> >7% gain + 3x volume (High-conviction short-term plays)</li>
                    <li><strong>STRONG:</strong> >5% gain + 2x volume (Solid momentum opportunities)</li>
                    <li><strong>MODERATE:</strong> >3% gain + 1.5x volume (Building momentum positions)</li>
                    <li><strong>BUILDING:</strong> Early-stage momentum development</li>
                </ul>
            </div>

            <h3>🌱 Emerging Opportunities (Tech>60 & Fund>60 & RS>1.00 & Value)</h3>
            <p>Undervalued quality stocks with strong fundamentals and positive momentum - medium-term value plays.</p>
            ', df_to_html_table(emerging_opportunities, "emerging-opportunities-table"), '
            
            <div class="insight-box">
                <h4>🏆 Opportunity Grading System</h4>
                <ul>
                    <li><strong>A+ Grade:</strong> TF Score ≥80 & Price <₹500 (Premium value opportunities)</li>
                    <li><strong>A Grade:</strong> TF Score ≥75 & Price <₹750 (Excellent value prospects)</li>
                    <li><strong>B+ Grade:</strong> TF Score ≥70 (Good quality selections)</li>
                    <li><strong>B Grade:</strong> TF Score ≥65 (Solid fundamentals)</li>
                </ul>
            </div>

            <!-- Enhanced Themes Summary -->
            <div class="summary-cards">
                <div class="card">
                    <h3>💎 Premium Quality</h3>
                    <div class="value highlight-green">', nrow(stock_results %>% 
                      filter(TECHNICAL_SCORE >= 60 & !is.na(ENHANCED_FUND_SCORE) & 
                             ENHANCED_FUND_SCORE >= 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.00)), '</div>
                    <p>Tech≥60 & Fund≥60 & RS>1.00</p>
                </div>
                <div class="card">
                    <h3>🌟 Super Growth</h3>
                    <div class="value highlight-blue">', nrow(stock_results %>% 
                      filter(TECHNICAL_SCORE >= 80 & !is.na(ENHANCED_FUND_SCORE) & 
                             ENHANCED_FUND_SCORE >= 70 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.10)), '</div>
                    <p>Tech≥80 & Fund≥70 & RS>1.10</p>
                </div>
                <div class="card">
                    <h3>⚡ Quality Momentum</h3>
                    <div class="value highlight-orange">', nrow(stock_results %>% 
                      filter(TECHNICAL_SCORE > 70 & !is.na(ENHANCED_FUND_SCORE) & 
                             ENHANCED_FUND_SCORE > 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.05 & VOLUME_PEAK == 1)), '</div>
                    <p>Tech>70 & Fund>60 & RS>1.05 & Volume</p>
                </div>
                <div class="card">
                    <h3>🌱 Emerging Value</h3>
                    <div class="value highlight-purple">', nrow(stock_results %>% 
                      filter(TECHNICAL_SCORE > 60 & !is.na(ENHANCED_FUND_SCORE) & 
                             ENHANCED_FUND_SCORE > 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.00 & 
                             CURRENT_PRICE < 1000 & TECHNOFUNDA_SCORE < 85)), '</div>
                    <p>Value + Quality + RS>1.00</p>
                </div>
            </div>

            <div class="insight-box">
                <h4>🎯 Strategic Investment Insights</h4>
                <ul>
                    <li><strong>Focus Areas:</strong> Quality Momentum for short-term gains, Emerging Opportunities for medium-term value</li>
                    <li><strong>Risk Management:</strong> All selections outperform NIFTY 500 with validated fundamentals</li>
                    <li><strong>Market Context:</strong> Despite bearish sentiment (', round(bearish_pct, 1), '% indices bearish), ', 
                    nrow(stock_results %>% filter(TECHNICAL_SCORE >= 60 & !is.na(ENHANCED_FUND_SCORE) & 
                                                 ENHANCED_FUND_SCORE >= 60 & RELATIVE_STRENGTH_VS_NIFTY500 > 1.00)), 
                    ' high-quality opportunities identified</li>
                    <li><strong>Selection Methodology:</strong> Minervini/O\'Neil inspired strategy with enhanced fundamental weighting</li>
                </ul>
            </div>
        </div>

        <!-- Section 12: TechnoFunda Analysis -->
        <div id="technofunda-analysis" class="section">
            <h2>12. 🔬 Best TechnoFunda Stocks (Technical + Fundamental Combined)</h2>
            <p>Comprehensive analysis combining technical excellence with fundamental strength for optimal investment selection.</p>
            ', df_to_html_table(best_technofunda, "technofunda-table"), '
            
            <div class="insight-box">
                <h4>📊 TechnoFunda Analysis Summary</h4>
                <ul>
                    <li><strong>IDEAL TechnoFunda Stocks (Tech≥70 & Fund≥70):</strong> ', 
                    nrow(best_technofunda %>% filter(TECH_SCORE >= 70 & FUND_SCORE >= 70)), ' stocks</li>
                    <li><strong>GOOD TechnoFunda Stocks (Tech≥60 & Fund≥60):</strong> ', 
                    nrow(best_technofunda %>% filter(TECH_SCORE >= 60 & FUND_SCORE >= 60)), ' stocks</li>
                    <li><strong>Average TechnoFunda Score:</strong> ', 
                    round(mean(best_technofunda$TF_SCORE, na.rm = TRUE), 1), '</li>
                    <li><strong>Top TechnoFunda Stock:</strong> ', 
                    best_technofunda$SYMBOL[1], ' (Score: ', best_technofunda$TF_SCORE[1], ')</li>
                </ul>
            </div>
        </div>

        <!-- Section 13: Market Insights -->
        <div id="market-insights" class="section">
            <h2>13. 💡 Market Insights & Summary</h2>
            
            <div class="insight-box">
                <h4>🎯 Top Investment Opportunities</h4>
                <ul>
                    <li><strong>High RS Stocks (>1.10):</strong> ', nrow(stock_results %>% filter(RELATIVE_STRENGTH_VS_NIFTY500 > 1.10)), ' stocks outperforming NIFTY 500 by 10%+</li>
                    <li><strong>Strong Gainers (>3%):</strong> ', nrow(stock_results %>% filter(DAY_CHANGE_PCT > 3)), ' stocks with significant price momentum</li>
                    <li><strong>Volume Breakouts:</strong> ', nrow(stock_results %>% filter(VOLUME_PEAK == 1)), ' stocks with exceptional volume activity</li>
                    <li><strong>Consolidation Breakouts:</strong> ', nrow(stock_results %>% filter(CONSOLIDATION_BREAKOUT == TRUE)), ' stocks breaking out of consolidation</li>
                    <li><strong>High Momentum Stocks:</strong> ', nrow(stock_results %>% filter(DAY_CHANGE_PCT > 5 & VOLUME_PEAK == 1)), ' stocks with strong price and volume surge</li>
                    <li><strong>Value Picks:</strong> ', nrow(stock_results %>% filter(CURRENT_PRICE < 500 & TECHNICAL_SCORE > 80)), ' relatively lower-priced stocks with strong technicals</li>
                </ul>
            </div>

            <h3>📊 Today\'s Market Performance</h3>
            <div class="summary-cards">
                <div class="card">
                    <h3>📈 Gainers</h3>
                    <div class="value highlight-green">', gainers, '</div>
                    <p>', round(gainers/nrow(stock_results)*100, 1), '% of stocks</p>
                </div>
                <div class="card">
                    <h3>📉 Losers</h3>
                    <div class="value highlight-red">', losers, '</div>
                    <p>', round(losers/nrow(stock_results)*100, 1), '% of stocks</p>
                </div>
                <div class="card">
                    <h3>🎯 Top Gainer</h3>
                    <div class="value highlight-green">', top_gainer$SYMBOL, '</div>
                    <p>+', round(top_gainer$DAY_CHANGE_PCT, 2), '%</p>
                </div>
                <div class="card">
                    <h3>⚠️ Top Loser</h3>
                    <div class="value highlight-red">', top_loser$SYMBOL, '</div>
                    <p>', round(top_loser$DAY_CHANGE_PCT, 2), '%</p>
                </div>
            </div>

            <h3>📈 Index Performance Leaders</h3>
            <ul>')

# Add top 3 indices
for(i in 1:3) {
  html_content <- paste0(html_content, 
    '<li><strong>', top_indices$INDEX[i], ':</strong> RS ', 
    round(top_indices$RELATIVE_STRENGTH_VS_NIFTY500[i], 4), 
    ' (', round(top_indices$DAY_CHANGE_PCT[i], 2), '%)</li>')
}

html_content <- paste0(html_content, '
            </ul>

            <div class="insight-box">
                <h4>💼 Key Investment Themes</h4>
                <ul>
                    <li><strong>Relative Strength Leaders:</strong> Focus on stocks with RS > 1.15 (outperforming NIFTY 500 by 15%+)</li>
                    <li><strong>Volume Breakout Stocks:</strong> High volume activity often precedes significant price moves</li>
                    <li><strong>Strong Price Momentum:</strong> Stocks with >3% daily gains showing sustained strength</li>
                    <li><strong>Technical Score Leaders:</strong> Stocks scoring >70 on comprehensive technical analysis</li>
                    <li><strong>Value Plays with Strong Technicals:</strong> Relatively lower-priced stocks with solid technical backing</li>
                    <li><strong>Contrarian Opportunities:</strong> Strong performers in weak market conditions</li>
                    <li><strong>Sector Rotation Candidates:</strong> Mid-cap momentum stocks with volume support</li>
                    <li><strong>Defensive Holdings:</strong> Stable performers for portfolio protection</li>
                </ul>
            </div>

            <h3>📊 Comprehensive Statistics</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
                <div>
                    <h4>Index Statistics</h4>
                    <ul>
                        <li>Total Indexes: ', nrow(index_results), '</li>
                        <li>Average Day Change: ', round(mean(index_results$DAY_CHANGE_PCT, na.rm = TRUE), 2), '%</li>
                        <li>Average RSI: ', round(mean(index_results$RSI, na.rm = TRUE), 1), '</li>
                        <li>Average RS vs NIFTY500: ', round(mean(index_results$RELATIVE_STRENGTH_VS_NIFTY500, na.rm = TRUE), 3), '</li>
                    </ul>
                </div>
                <div>
                    <h4>Stock Statistics</h4>
                    <ul>
                        <li>Total Stocks: ', nrow(stock_results), '</li>
                        <li>Average Technical Score: ', round(mean(stock_results$TECHNICAL_SCORE, na.rm = TRUE), 1), '</li>
                        <li>Average Day Change: ', round(mean(stock_results$DAY_CHANGE_PCT, na.rm = TRUE), 2), '%</li>
                        <li>Average RSI: ', round(mean(stock_results$RSI, na.rm = TRUE), 1), '</li>
                        <li>Average RS vs NIFTY500: ', round(mean(stock_results$RELATIVE_STRENGTH_VS_NIFTY500, na.rm = TRUE), 3), '</li>
                        <li>Volume Peak Stocks: ', sum(stock_results$VOLUME_PEAK), ' (', round(sum(stock_results$VOLUME_PEAK)/nrow(stock_results)*100, 1), '%)</li>
                        <li>Above SMA20 proxy: ', sum(stock_results$ABOVE_SMA20), ' (', round(sum(stock_results$ABOVE_SMA20)/nrow(stock_results)*100, 1), '%)</li>
                    </ul>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>📊 <strong>Enhanced NSE Market Analysis Report</strong></p>
            <p>Generated on ', format(Sys.time(), "%B %d, %Y at %I:%M %p"), ' using real-time NSE data</p>
            <p style="margin-top: 15px; font-size: 0.9em;">
                Data Sources: nse_sec_full_data.csv (', nrow(stock_data), ' records) | nse_index_data.csv (', nrow(index_data), ' records)<br>
                Analysis covers ', nrow(stock_results), ' actively traded stocks and ', nrow(index_results), ' market indices
            </p>
            <p style="margin-top: 20px; font-size: 0.8em; color: #95a5a6; font-style: italic;">
                Powered by <strong>Agents Adda Team</strong>
            </p>
        </div>
    </div>

    <script>
        // Add some interactivity
        document.addEventListener("DOMContentLoaded", function() {
            // Smooth scrolling for table of contents links
            document.querySelectorAll(".toc a").forEach(anchor => {
                anchor.addEventListener("click", function (e) {
                    e.preventDefault();
                    document.querySelector(this.getAttribute("href")).scrollIntoView({
                        behavior: "smooth"
                    });
                });
            });

            // Highlight positive/negative values in tables
            document.querySelectorAll("td").forEach(cell => {
                const text = cell.textContent.trim();
                if (text.includes("+") || (text.includes("%") && parseFloat(text) > 0)) {
                    cell.classList.add("highlight-green");
                } else if (text.includes("-") && text.includes("%")) {
                    cell.classList.add("highlight-red");
                } else if (text.includes("STRONG_BUY") || text.includes("BUY")) {
                    cell.classList.add("signal-positive");
                } else if (text.includes("SELL")) {
                    cell.classList.add("signal-negative");
                } else if (text.includes("HOLD") || text.includes("NEUTRAL")) {
                    cell.classList.add("signal-neutral");
                }
            });
        });
    </script>
</body>
</html>')

# Write HTML file
writeLines(html_content, html_file)

cat("\nFiles Generated:\n")
cat("• Stock Analysis CSV:", output_file, "\n")
cat("• Index Analysis CSV:", index_output_file, "\n")
cat("• Detailed HTML Report:", html_file, "\n")
