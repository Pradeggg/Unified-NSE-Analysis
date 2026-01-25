# =============================================================================
# COMPREHENSIVE MARKET BREADTH ANALYSIS
# Analyzes market breadth for ALL major NSE indices
# Shows percentage of stocks above/below key DMAs (20, 50, 100, 200)
# =============================================================================

library(dplyr)
library(TTR)
library(lubridate)
library(jsonlite)

# =============================================================================
# Configuration
# =============================================================================
data_dir <- "data"
reports_dir <- "reports"

# =============================================================================
# Load Index Constituents from CSV File
# =============================================================================
index_mapping_file <- file.path(data_dir, "index_stock_mapping.csv")

if(file.exists(index_mapping_file)) {
  cat("Loading index constituents from:", index_mapping_file, "\n")
  index_mapping <- read.csv(index_mapping_file, stringsAsFactors = FALSE)
  
  # Normalize index names to uppercase to handle case variations (e.g., "Nifty 50" vs "NIFTY 50")
  index_mapping$INDEX_NAME_NORMALIZED <- toupper(trimws(index_mapping$INDEX_NAME))
  
  # First, group by original name to get stock counts for each variation
  original_groups <- split(index_mapping$STOCK_SYMBOL, index_mapping$INDEX_NAME)
  
  # For each normalized index name, find the original name with the most stocks
  normalized_names <- unique(index_mapping$INDEX_NAME_NORMALIZED)
  index_constituents <- list()
  
  for(norm_name in normalized_names) {
    # Get all original names that map to this normalized name
    original_names <- unique(index_mapping$INDEX_NAME[index_mapping$INDEX_NAME_NORMALIZED == norm_name])
    
    if(length(original_names) > 1) {
      # Multiple versions exist - find the one with most stocks
      max_stocks <- 0
      best_original_name <- NULL
      best_stocks <- NULL
      
      for(orig_name in original_names) {
        stocks <- original_groups[[orig_name]]
        stock_count <- length(unique(stocks))  # Count unique stocks
        if(stock_count > max_stocks) {
          max_stocks <- stock_count
          best_original_name <- orig_name
          best_stocks <- unique(stocks)  # Get unique stocks
        }
      }
      index_constituents[[norm_name]] <- as.character(best_stocks)
      cat("Merged duplicate index:", paste(original_names, collapse = " / "), 
          "-> Using", best_original_name, "with", length(best_stocks), "stocks (normalized as", norm_name, ")\n")
    } else {
      # Single version - use it
      orig_name <- original_names[1]
      stocks <- unique(original_groups[[orig_name]])
      index_constituents[[norm_name]] <- as.character(stocks)
    }
  }
  
  cat("✅ Loaded", length(index_constituents), "indices from mapping file (after merging duplicates)\n")
  cat("Sample indices:", paste(head(names(index_constituents), 10), collapse = ", "), "...\n\n")
} else {
  cat("⚠️ Index mapping file not found. Using fallback hardcoded list.\n")
  # Fallback to basic indices if file doesn't exist
  index_constituents <- list(
    "Nifty 50" = c("RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN"),
    "Nifty Bank" = c("HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK")
  )
}

# =============================================================================
# Load Stock Data
# =============================================================================
cat("=== COMPREHENSIVE MARKET BREADTH ANALYSIS ===\n")
cat("Loading stock data...\n")

# Load from cache if available
stock_data <- NULL
if(file.exists(file.path(data_dir, "nse_stock_cache.RData"))) {
  load(file.path(data_dir, "nse_stock_cache.RData"))
  if(exists("nse_stock_data")) {
    stock_data <- nse_stock_data
    cat("✅ Loaded stock data from cache:", nrow(stock_data), "records\n")
  }
}

# If no cache, load from CSV
if(is.null(stock_data)) {
  stock_data_file <- file.path(data_dir, "nse_sec_full_data.csv")
  if(file.exists(stock_data_file)) {
    stock_data <- read.csv(stock_data_file, stringsAsFactors = FALSE)
    cat("✅ Loaded stock data from CSV:", nrow(stock_data), "records\n")
  } else {
    stop("Stock data file not found!")
  }
}

# Convert TIMESTAMP to Date
stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)

# Get latest date
latest_date <- max(stock_data$TIMESTAMP, na.rm = TRUE)
cat("Latest data date:", as.character(latest_date), "\n")

# Get unique stocks
all_stocks <- unique(stock_data$SYMBOL)
cat("Total unique stocks:", length(all_stocks), "\n")

# =============================================================================
# Function to Calculate DMA Analysis for a Stock
# =============================================================================
calculate_stock_dma <- function(symbol, stock_data, min_days = 200) {
  tryCatch({
    # Get stock history
    stock_history <- stock_data %>%
      filter(SYMBOL == symbol) %>%
      filter(!is.na(CLOSE) & CLOSE > 0) %>%
      arrange(TIMESTAMP) %>%
      select(SYMBOL, TIMESTAMP, CLOSE)
    
    if(nrow(stock_history) < min_days) {
      return(NULL)
    }
    
    # Get latest price
    latest_price <- stock_history$CLOSE[nrow(stock_history)]
    
    # Calculate SMAs
    prices <- stock_history$CLOSE
    sma_20 <- tryCatch(tail(SMA(prices, n = 20), 1), error = function(e) NA)
    sma_50 <- tryCatch(tail(SMA(prices, n = 50), 1), error = function(e) NA)
    sma_100 <- tryCatch(tail(SMA(prices, n = 100), 1), error = function(e) NA)
    sma_200 <- tryCatch(tail(SMA(prices, n = 200), 1), error = function(e) NA)
    
    # Check if price is above each DMA
    above_20 <- !is.na(sma_20) && latest_price > sma_20
    above_50 <- !is.na(sma_50) && latest_price > sma_50
    above_100 <- !is.na(sma_100) && latest_price > sma_100
    above_200 <- !is.na(sma_200) && latest_price > sma_200
    
    return(data.frame(
      SYMBOL = symbol,
      CURRENT_PRICE = latest_price,
      SMA_20 = sma_20,
      SMA_50 = sma_50,
      SMA_100 = sma_100,
      SMA_200 = sma_200,
      ABOVE_20DMA = above_20,
      ABOVE_50DMA = above_50,
      ABOVE_100DMA = above_100,
      ABOVE_200DMA = above_200,
      stringsAsFactors = FALSE
    ))
  }, error = function(e) {
    return(NULL)
  })
}

# =============================================================================
# Function to Calculate Market Breadth for an Index
# =============================================================================
calculate_index_breadth <- function(index_name, stock_symbols, stock_data) {
  cat("\nAnalyzing", index_name, "...\n")
  cat("Constituent stocks:", length(stock_symbols), "\n")
  
  # Filter stocks that exist in our data
  available_stocks <- stock_symbols[stock_symbols %in% unique(stock_data$SYMBOL)]
  cat("Available in data:", length(available_stocks), "\n")
  
  if(length(available_stocks) == 0) {
    return(NULL)
  }
  
  # Calculate DMA for each stock
  dma_results <- data.frame(
    SYMBOL = character(),
    CURRENT_PRICE = numeric(),
    SMA_20 = numeric(),
    SMA_50 = numeric(),
    SMA_100 = numeric(),
    SMA_200 = numeric(),
    ABOVE_20DMA = logical(),
    ABOVE_50DMA = logical(),
    ABOVE_100DMA = logical(),
    ABOVE_200DMA = logical(),
    stringsAsFactors = FALSE
  )
  
  processed <- 0
  for(symbol in available_stocks) {
    result <- calculate_stock_dma(symbol, stock_data)
    if(!is.null(result)) {
      dma_results <- rbind(dma_results, result)
      processed <- processed + 1
      if(processed %% 10 == 0) {
        cat("  Processed", processed, "stocks...\n")
      }
    }
  }
  
  cat("✅ Successfully processed", processed, "stocks\n")
  
  if(nrow(dma_results) == 0) {
    return(NULL)
  }
  
  total_stocks <- nrow(dma_results)
  
  # Calculate percentages
  breadth_200 <- sum(dma_results$ABOVE_200DMA, na.rm = TRUE)
  pct_above_200 <- round((breadth_200 / total_stocks) * 100, 2)
  pct_below_200 <- round(100 - pct_above_200, 2)
  
  breadth_100 <- sum(dma_results$ABOVE_100DMA, na.rm = TRUE)
  pct_above_100 <- round((breadth_100 / total_stocks) * 100, 2)
  pct_below_100 <- round(100 - pct_above_100, 2)
  
  breadth_50 <- sum(dma_results$ABOVE_50DMA, na.rm = TRUE)
  pct_above_50 <- round((breadth_50 / total_stocks) * 100, 2)
  pct_below_50 <- round(100 - pct_above_50, 2)
  
  breadth_20 <- sum(dma_results$ABOVE_20DMA, na.rm = TRUE)
  pct_above_20 <- round((breadth_20 / total_stocks) * 100, 2)
  pct_below_20 <- round(100 - pct_above_20, 2)
  
  # Assess breadth
  assess_breadth <- function(pct_above) {
    if(pct_above >= 70) {
      return(list(status = "STRONG", color = "green", icon = "🟢"))
    } else if(pct_above >= 50) {
      return(list(status = "MODERATE", color = "yellow", icon = "🟡"))
    } else {
      return(list(status = "WEAK", color = "red", icon = "🔴"))
    }
  }
  
  avg_breadth <- mean(c(pct_above_200, pct_above_100, pct_above_50, pct_above_20))
  overall_assessment <- assess_breadth(avg_breadth)
  
  # Calculate score for each stock (number of DMAs above)
  dma_results$DMA_SCORE <- rowSums(dma_results[, c("ABOVE_200DMA", "ABOVE_100DMA", "ABOVE_50DMA", "ABOVE_20DMA")], na.rm = TRUE)
  
  # Get top 10 stocks by DMA score (then by price if tied)
  top_10_stocks <- dma_results %>%
    arrange(desc(DMA_SCORE), desc(CURRENT_PRICE)) %>%
    head(10) %>%
    mutate(
      DMA_STATUS = paste0(
        ifelse(ABOVE_200DMA, "✓200", ""),
        ifelse(ABOVE_100DMA, " ✓100", ""),
        ifelse(ABOVE_50DMA, " ✓50", ""),
        ifelse(ABOVE_20DMA, " ✓20", "")
      )
    )
  
  return(list(
    index_name = index_name,
    total_stocks = total_stocks,
    breadth_200 = breadth_200,
    breadth_100 = breadth_100,
    breadth_50 = breadth_50,
    breadth_20 = breadth_20,
    pct_above_200 = pct_above_200,
    pct_below_200 = pct_below_200,
    pct_above_100 = pct_above_100,
    pct_below_100 = pct_below_100,
    pct_above_50 = pct_above_50,
    pct_below_50 = pct_below_50,
    pct_above_20 = pct_above_20,
    pct_below_20 = pct_below_20,
    assessment_200 = assess_breadth(pct_above_200),
    assessment_100 = assess_breadth(pct_above_100),
    assessment_50 = assess_breadth(pct_above_50),
    assessment_20 = assess_breadth(pct_above_20),
    avg_breadth = avg_breadth,
    overall_assessment = overall_assessment,
    dma_results = dma_results,
    top_10_stocks = top_10_stocks
  ))
}

# =============================================================================
# Calculate Market Breadth for All Indices
# =============================================================================
cat("\n=== CALCULATING MARKET BREADTH FOR ALL INDICES ===\n")

# For NIFTY500, use all stocks with sufficient data
cat("\nFiltering stocks with sufficient historical data (≥200 days) for NIFTY500...\n")
stocks_with_sufficient_data <- c()
min_days_required <- 200

for(symbol in all_stocks) {
  stock_history <- stock_data %>%
    filter(SYMBOL == symbol) %>%
    filter(!is.na(CLOSE) & CLOSE > 0) %>%
    arrange(TIMESTAMP) %>%
    select(SYMBOL, TIMESTAMP, CLOSE)
  
  if(nrow(stock_history) >= min_days_required) {
    stocks_with_sufficient_data <- c(stocks_with_sufficient_data, symbol)
  }
}

cat("✅ Stocks with ≥200 days of data:", length(stocks_with_sufficient_data), "\n")

# Check if NIFTY 500 exists in CSV (use normalized uppercase name)
nifty500_name <- NULL
if("NIFTY 500" %in% names(index_constituents)) {
  nifty500_name <- "NIFTY 500"
} else if("NIFTY500" %in% names(index_constituents)) {
  nifty500_name <- "NIFTY500"
}

if(!is.null(nifty500_name)) {
  cat("\n✅ Using NIFTY 500 from CSV mapping file:", length(index_constituents[[nifty500_name]]), "stocks\n")
  nifty500_stocks <- index_constituents[[nifty500_name]]
} else {
  # For NIFTY500, select top 500 stocks by trading volume from stocks with sufficient data
  # This approximates the actual NIFTY500 index which includes the top 500 stocks by market cap
  cat("\nNIFTY 500 not found in CSV. Identifying top 500 stocks for NIFTY500 (by trading volume)...\n")
  latest_date <- max(stock_data$TIMESTAMP, na.rm = TRUE)
  nifty500_stocks <- stock_data %>%
    filter(TIMESTAMP == latest_date) %>%
    filter(SYMBOL %in% stocks_with_sufficient_data) %>%
    arrange(desc(TOTTRDQTY)) %>%
    head(500) %>%
    pull(SYMBOL)
  
  cat("✅ Identified", length(nifty500_stocks), "stocks for NIFTY500\n")
  
  # Add NIFTY500 to index constituents (use "NIFTY 500" to match CSV format)
  index_constituents[["NIFTY 500"]] <- nifty500_stocks
}

# For NIFTY SMLCAP 250, use all stocks with sufficient data that are NOT in major indices
# (Nifty 50, 100, 200, 500) to get a representative sample of small cap stocks
cat("\nIdentifying stocks for NIFTY SMLCAP 250 (excluding Nifty 50, 100, 200, 500)...\n")
# Safely get major index stocks (handle cases where indices might not exist in CSV)
# Use normalized (uppercase) index names
major_index_stocks <- unique(c(
  if("NIFTY 50" %in% names(index_constituents)) index_constituents[["NIFTY 50"]] else NULL,
  if("NIFTY 100" %in% names(index_constituents)) index_constituents[["NIFTY 100"]] else NULL,
  if("NIFTY 200" %in% names(index_constituents)) index_constituents[["NIFTY 200"]] else NULL,
  nifty500_stocks  # Use NIFTY 500 stocks (from CSV or dynamically generated)
))

# Get small cap stocks (stocks with sufficient data but not in major indices)
# Limit to top 250 by trading volume to approximate the actual index
latest_stock_data <- stock_data %>%
  filter(TIMESTAMP == latest_date) %>%
  filter(SYMBOL %in% stocks_with_sufficient_data) %>%
  filter(!SYMBOL %in% major_index_stocks) %>%
  arrange(desc(TOTTRDQTY)) %>%
  head(250) %>%
  pull(SYMBOL)

cat("✅ Identified", length(latest_stock_data), "stocks for NIFTY SMLCAP 250\n")

# Check if NIFTY SMLCAP 250 already exists in CSV (if not, add the dynamically generated one)
if(!"NIFTY SMLCAP 250" %in% names(index_constituents)) {
  # Add NIFTY SMLCAP 250 to index constituents
  index_constituents[["NIFTY SMLCAP 250"]] <- latest_stock_data
} else {
  cat("✅ Using NIFTY SMLCAP 250 from CSV mapping file:", length(index_constituents[["NIFTY SMLCAP 250"]]), "stocks\n")
}

# Calculate breadth for each index
index_results <- list()
for(index_name in names(index_constituents)) {
  result <- calculate_index_breadth(index_name, index_constituents[[index_name]], stock_data)
  if(!is.null(result)) {
    index_results[[index_name]] <- result
  }
}

# =============================================================================
# Generate Comprehensive HTML Report
# =============================================================================
cat("\nGenerating comprehensive HTML report...\n")

timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
report_file <- file.path(reports_dir, paste0("Comprehensive_Market_Breadth_", timestamp, ".html"))

# Build HTML content
html_parts <- c('
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comprehensive Market Breadth Analysis</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: "Roboto", "Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #212121;
            font-weight: 400;
            line-height: 1.6;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            color: white;
        }
        
        .header h1 {
            font-size: 3rem;
            font-weight: 300;
            margin-bottom: 16px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
            letter-spacing: -0.5px;
        }
        
        .header p {
            font-size: 1.25rem;
            font-weight: 400;
            opacity: 0.95;
            letter-spacing: 0.2px;
        }
        
        .index-section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .index-section h2 {
            color: #1976d2;
            margin-bottom: 24px;
            font-size: 1.8rem;
            font-weight: 500;
            letter-spacing: 0.2px;
            border-bottom: 2px solid #1976d2;
            padding-bottom: 12px;
        }
        
        .index-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        
        .summary-card {
            background: rgba(0,0,0,0.02);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        
        .summary-value {
            font-size: 2.5rem;
            font-weight: 300;
            color: #1976d2;
            margin-bottom: 8px;
        }
        
        .summary-label {
            font-size: 0.875rem;
            color: #616161;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }
        
        .breadth-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        
        .breadth-card {
            background: rgba(255, 255, 255, 0.8);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
            border: 1px solid rgba(0,0,0,0.05);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border-left: 5px solid;
        }
        
        .breadth-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.15);
        }
        
        .breadth-card.strong {
            border-left-color: #4caf50;
        }
        
        .breadth-card.moderate {
            border-left-color: #ff9800;
        }
        
        .breadth-card.weak {
            border-left-color: #f44336;
        }
        
        .breadth-card h3 {
            font-size: 1.25rem;
            font-weight: 500;
            margin-bottom: 16px;
            color: #212121;
        }
        
        .breadth-stats {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 16px 0;
        }
        
        .stat-item {
            text-align: center;
            flex: 1;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: 300;
            margin-bottom: 8px;
            line-height: 1;
        }
        
        .stat-label {
            font-size: 0.875rem;
            color: #616161;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }
        
        .stat-value.above {
            color: #4caf50;
        }
        
        .stat-value.below {
            color: #f44336;
        }
        
        .progress-bar {
            width: 100%;
            height: 32px;
            background: rgba(0,0,0,0.05);
            border-radius: 16px;
            overflow: hidden;
            margin: 16px 0;
            position: relative;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4caf50 0%, #8bc34a 100%);
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 500;
            font-size: 0.875rem;
        }
        
        .progress-fill.moderate {
            background: linear-gradient(90deg, #ff9800 0%, #ffb74d 100%);
        }
        
        .progress-fill.weak {
            background: linear-gradient(90deg, #f44336 0%, #e57373 100%);
        }
        
        .assessment-badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 16px;
            font-weight: 500;
            margin-top: 12px;
            font-size: 0.875rem;
        }
        
        .assessment-badge.strong {
            background: #4caf50;
            color: white;
        }
        
        .assessment-badge.moderate {
            background: #ff9800;
            color: white;
        }
        
        .assessment-badge.weak {
            background: #f44336;
            color: white;
        }
        
        .overall-assessment {
            background: rgba(25, 118, 210, 0.1);
            border-radius: 12px;
            padding: 24px;
            text-align: center;
            margin-top: 24px;
        }
        
        .overall-value {
            font-size: 3rem;
            font-weight: 300;
            margin: 16px 0;
            color: #1976d2;
            line-height: 1;
        }
        
        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 30px;
        }
        
        .comparison-table th,
        .comparison-table td {
            padding: 16px;
            text-align: left;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }
        
        .comparison-table th {
            background: rgba(0,0,0,0.02);
            font-weight: 500;
            color: #1976d2;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }
        
        .comparison-table td {
            color: #212121;
            font-size: 0.9375rem;
        }
        
        .comparison-table tr:hover {
            background: rgba(25, 118, 210, 0.05);
        }
        
        .footer {
            text-align: center;
            padding: 24px;
            color: rgba(255, 255, 255, 0.9);
            font-size: 0.875rem;
            margin-top: 30px;
        }
        
        .footer p {
            margin: 4px 0;
        }
        
        .search-container {
            margin: 24px 0;
            position: relative;
        }
        
        .search-box {
            width: 100%;
            max-width: 500px;
            padding: 14px 20px 14px 50px;
            font-size: 1rem;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            outline: none;
        }
        
        .search-box:focus {
            border-color: #1976d2;
            box-shadow: 0 4px 12px rgba(25, 118, 210, 0.2);
        }
        
        .search-box::placeholder {
            color: #9e9e9e;
        }
        
        .search-icon {
            position: absolute;
            left: 18px;
            top: 50%;
            transform: translateY(-50%);
            color: #9e9e9e;
            font-size: 1.2rem;
        }
        
        .no-results {
            text-align: center;
            padding: 40px;
            color: #9e9e9e;
            font-size: 1.1rem;
            display: none;
        }
        
        .index-section.hidden {
            display: none;
        }
        
        .index-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .view-stocks-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
        }
        
        .view-stocks-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            backdrop-filter: blur(4px);
        }
        
        .modal-content {
            background-color: white;
            margin: 5% auto;
            padding: 0;
            border-radius: 16px;
            width: 90%;
            max-width: 900px;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                transform: translateY(-50px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
        
        .modal-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 16px 16px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-header h3 {
            margin: 0;
            font-size: 1.5rem;
        }
        
        .close-modal {
            color: white;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            background: rgba(255,255,255,0.2);
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }
        
        .close-modal:hover {
            background: rgba(255,255,255,0.3);
            transform: rotate(90deg);
        }
        
        .modal-body {
            padding: 24px;
        }
        
        .stocks-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }
        
        .stocks-table th {
            background: #f5f5f5;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #424242;
            border-bottom: 2px solid #e0e0e0;
        }
        
        .stocks-table td {
            padding: 12px;
            border-bottom: 1px solid #f0f0f0;
        }
        
        .stocks-table tr:hover {
            background: #f9f9f9;
        }
        
        .stock-symbol {
            font-weight: 600;
            color: #1976d2;
        }
        
        .stock-price {
            font-weight: 500;
            color: #424242;
        }
        
        .dma-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin: 0 2px;
        }
        
        .dma-indicator.above {
            background: #4caf50;
        }
        
        .dma-indicator.below {
            background: #f44336;
        }
        
        .dma-score {
            font-weight: 600;
            color: #1976d2;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Comprehensive Market Breadth Analysis</h1>
            <p>Analysis Date: ', format(latest_date, "%B %d, %Y"), '</p>
            <p>Indices Analyzed: All Major NSE Indices (23+ indices including Nifty 50, Nifty Bank, Nifty IT, Nifty Auto, Nifty Pharma, Nifty FMCG, Nifty Metal, Nifty Energy, Nifty Realty, Nifty Consumer Durables, Nifty Infrastructure, Nifty Media, Nifty PSU Bank, Nifty Private Bank, Nifty Oil & Gas, Nifty 100, Nifty Next 50, Nifty 200, Nifty 500, Nifty Midcap 50, NIFTY SMLCAP 100/50/250, and more)</p>
            <div class="search-container">
                <span class="search-icon">🔍</span>
                <input type="text" id="indexSearch" class="search-box" placeholder="Search for an index (e.g., Nifty 50, Bank, IT, Auto...)">
            </div>
        </div>
        <div class="no-results" id="noResults">
            No indices found matching your search.
        </div>')

# Add index sections
for(index_name in names(index_results)) {
  result <- index_results[[index_name]]
  
  # Prepare top 10 stocks data as JSON for JavaScript (escape properly for HTML)
  top_10_data <- result$top_10_stocks[, c("SYMBOL", "CURRENT_PRICE", "ABOVE_200DMA", "ABOVE_100DMA", "ABOVE_50DMA", "ABOVE_20DMA", "DMA_SCORE")]
  top_10_json <- jsonlite::toJSON(top_10_data, pretty = FALSE)
  # Escape quotes and newlines for HTML attribute
  top_10_json_escaped <- gsub('"', '&quot;', top_10_json)
  top_10_json_escaped <- gsub("'", "&#39;", top_10_json_escaped)
  top_10_json_escaped <- gsub("\n", "", top_10_json_escaped)
  
  html_parts <- c(html_parts, paste0('
        <div class="index-section" data-index-name="', tolower(result$index_name), '">
            <div class="index-header">
            <h2>', result$index_name, '</h2>
                <button class="view-stocks-btn" data-index-name="', result$index_name, '" data-stocks-data="', top_10_json_escaped, '">
                    📈 View Top 10 Stocks
                </button>
            </div>
            
            <div class="index-summary">
                <div class="summary-card">
                    <div class="summary-value">', result$total_stocks, '</div>
                    <div class="summary-label">Total Stocks</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value">', round(result$avg_breadth, 2), '%</div>
                    <div class="summary-label">Avg Breadth</div>
                </div>
                <div class="summary-card">
                    <div class="summary-value ', tolower(result$overall_assessment$status), '">', result$overall_assessment$icon, '</div>
                    <div class="summary-label">', result$overall_assessment$status, '</div>
                </div>
            </div>
            
            <div class="breadth-grid">
                <div class="breadth-card ', tolower(result$assessment_200$status), '">
                    <h3>📈 200-Day Moving Average</h3>
                    <div class="breadth-stats">
                        <div class="stat-item">
                            <div class="stat-value above">', result$pct_above_200, '%</div>
                            <div class="stat-label">Above</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value below">', result$pct_below_200, '%</div>
                            <div class="stat-label">Below</div>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill ', tolower(result$assessment_200$status), '" style="width: ', result$pct_above_200, '%;">
                            ', result$pct_above_200, '%
                        </div>
                    </div>
                    <div class="assessment-badge ', tolower(result$assessment_200$status), '">
                        ', result$assessment_200$icon, ' ', result$assessment_200$status, '
                    </div>
                    <p style="margin-top: 12px; font-size: 0.875rem; color: #616161;">
                        ', result$breadth_200, ' stocks above / ', (result$total_stocks - result$breadth_200), ' stocks below
                    </p>
                </div>
                
                <div class="breadth-card ', tolower(result$assessment_100$status), '">
                    <h3>📊 100-Day Moving Average</h3>
                    <div class="breadth-stats">
                        <div class="stat-item">
                            <div class="stat-value above">', result$pct_above_100, '%</div>
                            <div class="stat-label">Above</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value below">', result$pct_below_100, '%</div>
                            <div class="stat-label">Below</div>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill ', tolower(result$assessment_100$status), '" style="width: ', result$pct_above_100, '%;">
                            ', result$pct_above_100, '%
                        </div>
                    </div>
                    <div class="assessment-badge ', tolower(result$assessment_100$status), '">
                        ', result$assessment_100$icon, ' ', result$assessment_100$status, '
                    </div>
                    <p style="margin-top: 12px; font-size: 0.875rem; color: #616161;">
                        ', result$breadth_100, ' stocks above / ', (result$total_stocks - result$breadth_100), ' stocks below
                    </p>
                </div>
                
                <div class="breadth-card ', tolower(result$assessment_50$status), '">
                    <h3>📉 50-Day Moving Average</h3>
                    <div class="breadth-stats">
                        <div class="stat-item">
                            <div class="stat-value above">', result$pct_above_50, '%</div>
                            <div class="stat-label">Above</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value below">', result$pct_below_50, '%</div>
                            <div class="stat-label">Below</div>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill ', tolower(result$assessment_50$status), '" style="width: ', result$pct_above_50, '%;">
                            ', result$pct_above_50, '%
                        </div>
                    </div>
                    <div class="assessment-badge ', tolower(result$assessment_50$status), '">
                        ', result$assessment_50$icon, ' ', result$assessment_50$status, '
                    </div>
                    <p style="margin-top: 12px; font-size: 0.875rem; color: #616161;">
                        ', result$breadth_50, ' stocks above / ', (result$total_stocks - result$breadth_50), ' stocks below
                    </p>
                </div>
                
                <div class="breadth-card ', tolower(result$assessment_20$status), '">
                    <h3>📊 20-Day Moving Average</h3>
                    <div class="breadth-stats">
                        <div class="stat-item">
                            <div class="stat-value above">', result$pct_above_20, '%</div>
                            <div class="stat-label">Above</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value below">', result$pct_below_20, '%</div>
                            <div class="stat-label">Below</div>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill ', tolower(result$assessment_20$status), '" style="width: ', result$pct_above_20, '%;">
                            ', result$pct_above_20, '%
                        </div>
                    </div>
                    <div class="assessment-badge ', tolower(result$assessment_20$status), '">
                        ', result$assessment_20$icon, ' ', result$assessment_20$status, '
                    </div>
                    <p style="margin-top: 12px; font-size: 0.875rem; color: #616161;">
                        ', result$breadth_20, ' stocks above / ', (result$total_stocks - result$breadth_20), ' stocks below
                    </p>
                </div>
            </div>
            
            <div class="overall-assessment">
                <h3 style="color: #1976d2; margin-bottom: 16px; font-size: 1.25rem;">Overall Market Breadth</h3>
                <div class="overall-value">', round(result$avg_breadth, 2), '%</div>
                <div class="assessment-badge ', tolower(result$overall_assessment$status), '" style="font-size: 1rem; padding: 10px 20px;">
                    ', result$overall_assessment$icon, ' ', result$overall_assessment$status, ' MARKET BREADTH
                </div>
            </div>
        </div>'))
}

# Add comparison table
html_parts <- c(html_parts, '
        <div class="index-section">
            <h2>Index Comparison</h2>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Index</th>
                        <th>Total Stocks</th>
                        <th>Above 200 DMA</th>
                        <th>Above 100 DMA</th>
                        <th>Above 50 DMA</th>
                        <th>Above 20 DMA</th>
                        <th>Avg Breadth</th>
                        <th>Assessment</th>
                    </tr>
                </thead>
                <tbody>')

for(index_name in names(index_results)) {
  result <- index_results[[index_name]]
  html_parts <- c(html_parts, paste0('
                    <tr data-index-name="', tolower(result$index_name), '">
                        <td><strong>', result$index_name, '</strong></td>
                        <td>', result$total_stocks, '</td>
                        <td>', result$pct_above_200, '% (', result$breadth_200, ')</td>
                        <td>', result$pct_above_100, '% (', result$breadth_100, ')</td>
                        <td>', result$pct_above_50, '% (', result$breadth_50, ')</td>
                        <td>', result$pct_above_20, '% (', result$breadth_20, ')</td>
                        <td><strong>', round(result$avg_breadth, 2), '%</strong></td>
                        <td><span class="assessment-badge ', tolower(result$overall_assessment$status), '">', result$overall_assessment$icon, ' ', result$overall_assessment$status, '</span></td>
                    </tr>'))
}

html_parts <- c(html_parts, '
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>Generated on ', format(Sys.time(), "%B %d, %Y at %I:%M %p"), '</p>
            <p>Comprehensive Market Breadth Analysis - Unified NSE Analysis System</p>
        </div>
    </div>
    
    <!-- Modal for Top 10 Stocks -->
    <div id="stocksModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="modalTitle">Top 10 Stocks</h3>
                <span class="close-modal" onclick="closeModal()">&times;</span>
            </div>
            <div class="modal-body">
                <table class="stocks-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Symbol</th>
                            <th>Current Price</th>
                            <th>200 DMA</th>
                            <th>100 DMA</th>
                            <th>50 DMA</th>
                            <th>20 DMA</th>
                            <th>DMA Score</th>
                        </tr>
                    </thead>
                    <tbody id="stocksTableBody">
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            const searchBox = document.getElementById("indexSearch");
            const indexSections = document.querySelectorAll(".index-section");
            const noResults = document.getElementById("noResults");
            const comparisonTable = document.querySelector(".comparison-table tbody");
            
            function filterIndices(searchTerm) {
                const term = searchTerm.toLowerCase().trim();
                let visibleCount = 0;
                
                // Filter index sections
                indexSections.forEach(section => {
                    const indexName = section.getAttribute("data-index-name");
                    if (term === "" || indexName.includes(term)) {
                        section.classList.remove("hidden");
                        visibleCount++;
                    } else {
                        section.classList.add("hidden");
                    }
                });
                
                // Filter comparison table rows
                if (comparisonTable) {
                    const rows = comparisonTable.querySelectorAll("tr");
                    rows.forEach(row => {
                        const indexCell = row.querySelector("td:first-child");
                        if (indexCell) {
                            const indexName = indexCell.textContent.toLowerCase();
                            if (term === "" || indexName.includes(term)) {
                                row.style.display = "";
                            } else {
                                row.style.display = "none";
                            }
                        }
                    });
                }
                
                // Show/hide no results message
                if (visibleCount === 0 && term !== "") {
                    noResults.style.display = "block";
                } else {
                    noResults.style.display = "none";
                }
            }
            
            // Add event listener for search input
            searchBox.addEventListener("input", function(e) {
                filterIndices(e.target.value);
            });
            
            // Add keyboard shortcut (Ctrl/Cmd + F focuses search)
            document.addEventListener("keydown", function(e) {
                if ((e.ctrlKey || e.metaKey) && e.key === "f") {
                    e.preventDefault();
                    searchBox.focus();
                }
            });
            
            // Add click handlers for View Top 10 Stocks buttons
            const viewStocksButtons = document.querySelectorAll(".view-stocks-btn");
            viewStocksButtons.forEach(function(button) {
                button.addEventListener("click", function() {
                    const indexName = this.getAttribute("data-index-name");
                    const stocksDataJson = this.getAttribute("data-stocks-data");
                    // Unescape HTML entities
                    const q = String.fromCharCode(34);
                    const stocksDataStr = stocksDataJson.replace(/&quot;/g, q).replace(/&#39;/g, "'");
                    try {
                        const stocksData = JSON.parse(stocksDataStr);
                        showTopStocks(indexName, stocksData);
                    } catch(e) {
                        console.error('Error parsing stocks data:', e);
                        alert('Error loading stock data. Please try again.');
                    }
                });
            });
        });
        
        // Function to show top 10 stocks modal
        function showTopStocks(indexName, stocksData) {
            const modal = document.getElementById('stocksModal');
            const modalTitle = document.getElementById('modalTitle');
            const tableBody = document.getElementById('stocksTableBody');
            
            modalTitle.textContent = 'Top 10 Stocks - ' + indexName;
            
            // Clear existing rows
            tableBody.innerHTML = '';
            
            // Add stock rows
            stocksData.forEach(function(stock, index) {
                const row = document.createElement('tr');
                const rank = index + 1;
                const price = parseFloat(stock.CURRENT_PRICE).toFixed(2);
                const dma200Class = stock.ABOVE_200DMA ? 'above' : 'below';
                const dma200Title = stock.ABOVE_200DMA ? 'Above' : 'Below';
                const dma100Class = stock.ABOVE_100DMA ? 'above' : 'below';
                const dma100Title = stock.ABOVE_100DMA ? 'Above' : 'Below';
                const dma50Class = stock.ABOVE_50DMA ? 'above' : 'below';
                const dma50Title = stock.ABOVE_50DMA ? 'Above' : 'Below';
                const dma20Class = stock.ABOVE_20DMA ? 'above' : 'below';
                const dma20Title = stock.ABOVE_20DMA ? 'Above' : 'Below';
                
                const td1 = document.createElement('td');
                td1.innerHTML = '<strong>' + rank + '</strong>';
                const td2 = document.createElement('td');
                const span1 = document.createElement('span');
                span1.className = 'stock-symbol';
                span1.textContent = stock.SYMBOL;
                td2.appendChild(span1);
                const td3 = document.createElement('td');
                const span2 = document.createElement('span');
                span2.className = 'stock-price';
                span2.textContent = '₹' + price;
                td3.appendChild(span2);
                const td4 = document.createElement('td');
                const span3 = document.createElement('span');
                span3.className = 'dma-indicator ' + dma200Class;
                span3.title = dma200Title;
                td4.appendChild(span3);
                const td5 = document.createElement('td');
                const span4 = document.createElement('span');
                span4.className = 'dma-indicator ' + dma100Class;
                span4.title = dma100Title;
                td5.appendChild(span4);
                const td6 = document.createElement('td');
                const span5 = document.createElement('span');
                span5.className = 'dma-indicator ' + dma50Class;
                span5.title = dma50Title;
                td6.appendChild(span5);
                const td7 = document.createElement('td');
                const span6 = document.createElement('span');
                span6.className = 'dma-indicator ' + dma20Class;
                span6.title = dma20Title;
                td7.appendChild(span6);
                const td8 = document.createElement('td');
                const span7 = document.createElement('span');
                span7.className = 'dma-score';
                span7.textContent = stock.DMA_SCORE + '/4';
                td8.appendChild(span7);
                row.appendChild(td1);
                row.appendChild(td2);
                row.appendChild(td3);
                row.appendChild(td4);
                row.appendChild(td5);
                row.appendChild(td6);
                row.appendChild(td7);
                row.appendChild(td8);
                tableBody.appendChild(row);
            });
            
            // Show modal
            modal.style.display = 'block';
        }
        
        // Function to close modal
        function closeModal() {
            const modal = document.getElementById('stocksModal');
            modal.style.display = 'none';
        }
        
        // Close modal when clicking outside of it
        window.onclick = function(event) {
            const modal = document.getElementById('stocksModal');
            if (event.target == modal) {
                closeModal();
            }
        }
        
        // Close modal with Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeModal();
            }
        });
    </script>
</body>
</html>')

# Write HTML file
html_content <- paste(html_parts, collapse = "")
writeLines(html_content, report_file)
cat("✅ HTML report saved to:", report_file, "\n")

# =============================================================================
# Print Summary
# =============================================================================
cat("\n=== COMPREHENSIVE MARKET BREADTH SUMMARY ===\n")
for(index_name in names(index_results)) {
  result <- index_results[[index_name]]
  cat("\n", result$index_name, ":\n", sep = "")
  cat("  Total Stocks: ", result$total_stocks, "\n", sep = "")
  cat("  200-Day DMA: ", result$pct_above_200, "% above / ", result$pct_below_200, "% below\n", sep = "")
  cat("  100-Day DMA: ", result$pct_above_100, "% above / ", result$pct_below_100, "% below\n", sep = "")
  cat("  50-Day DMA:  ", result$pct_above_50, "% above / ", result$pct_below_50, "% below\n", sep = "")
  cat("  20-Day DMA:  ", result$pct_above_20, "% above / ", result$pct_below_20, "% below\n", sep = "")
  cat("  Overall Breadth: ", round(result$avg_breadth, 2), "% (", result$overall_assessment$status, ")\n", sep = "")
}

cat("\n✅ Comprehensive analysis completed successfully!\n")




