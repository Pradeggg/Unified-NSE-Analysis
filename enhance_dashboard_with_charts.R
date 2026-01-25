# =============================================================================
# ENHANCE DASHBOARD WITH REAL STOCK CHARTS
# Adds actual historical price data to the NSE Interactive Dashboard
# =============================================================================

library(dplyr)
library(TTR)
library(lubridate)

# Configuration
data_dir <- "data"
reports_dir <- "reports"

cat("=== ENHANCING DASHBOARD WITH REAL STOCK CHARTS ===\n")

# Load stock data
cat("Loading stock data...\n")
if(file.exists(file.path(data_dir, "nse_stock_cache.RData"))) {
  load(file.path(data_dir, "nse_stock_cache.RData"))
  if(!exists("stock_data")) {
    # Try alternative variable names
    if(exists("nse_stock_data")) {
      stock_data <- nse_stock_data
    } else {
      stop("Stock data not found in cache")
    }
  }
  cat("✅ Loaded stock data:", nrow(stock_data), "records\n")
} else {
  stop("Stock data cache not found")
}

# Convert TIMESTAMP to Date
stock_data$TIMESTAMP <- as.Date(stock_data$TIMESTAMP)

# Get latest dashboard file
cat("Finding latest dashboard...\n")
dashboard_files <- list.files(reports_dir, pattern = "NSE_Interactive_Dashboard_.*\\.html$", full.names = TRUE)
if(length(dashboard_files) == 0) {
  stop("No dashboard file found")
}

latest_dashboard <- dashboard_files[which.max(file.mtime(dashboard_files))]
cat("Found dashboard:", basename(latest_dashboard), "\n")

# Read the dashboard HTML
dashboard_content <- readLines(latest_dashboard, warn = FALSE)
dashboard_text <- paste(dashboard_content, collapse = "\n")

# Extract stock symbols from the dashboard
cat("Extracting stock symbols from dashboard...\n")
# Find the stocksData array in JavaScript - use multiline pattern
stocks_data_match <- regexpr("const stocksData = \\[([\\s\\S]*?)\\];", dashboard_text, perl = TRUE)
if(stocks_data_match == -1) {
  stop("Could not find stocksData in dashboard")
}

# Function to get historical price data for a stock
get_stock_chart_data <- function(symbol, max_days = 200) {
  tryCatch({
    # Get stock history
    stock_history <- stock_data %>%
      filter(SYMBOL == symbol) %>%
      filter(!is.na(CLOSE) & CLOSE > 0) %>%
      arrange(TIMESTAMP) %>%
      select(TIMESTAMP, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY) %>%
      tail(max_days)
    
    if(nrow(stock_history) < 20) {
      return(NULL)
    }
    
    # Calculate moving averages
    prices <- stock_history$CLOSE
    volumes <- stock_history$TOTTRDQTY
    
    sma_20 <- tryCatch(SMA(prices, n = 20), error = function(e) rep(NA, length(prices)))
    sma_50 <- tryCatch(SMA(prices, n = 50), error = function(e) rep(NA, length(prices)))
    sma_100 <- tryCatch(SMA(prices, n = 100), error = function(e) rep(NA, length(prices)))
    sma_200 <- tryCatch(SMA(prices, n = 200), error = function(e) rep(NA, length(prices)))
    
    # Pad SMAs to match data length
    pad_na <- function(vec, target_len) {
      if(length(vec) < target_len) {
        c(rep(NA, target_len - length(vec)), vec)
      } else {
        vec
      }
    }
    
    sma_20 <- pad_na(sma_20, nrow(stock_history))
    sma_50 <- pad_na(sma_50, nrow(stock_history))
    sma_100 <- pad_na(sma_100, nrow(stock_history))
    sma_200 <- pad_na(sma_200, nrow(stock_history))
    
    # Create chart data
    chart_data <- data.frame(
      date = stock_history$TIMESTAMP,
      open = stock_history$OPEN,
      high = stock_history$HIGH,
      low = stock_history$LOW,
      close = stock_history$CLOSE,
      volume = stock_history$TOTTRDQTY,
      sma20 = sma_20,
      sma50 = sma_50,
      sma100 = sma_100,
      sma200 = sma_200
    )
    
    return(chart_data)
  }, error = function(e) {
    return(NULL)
  })
}

# Function to convert chart data to JavaScript format
chart_data_to_js <- function(chart_data) {
  if(is.null(chart_data) || nrow(chart_data) == 0) {
    return("[]")
  }
  
  js_lines <- c()
  for(i in 1:nrow(chart_data)) {
    row <- chart_data[i, ]
    js_line <- sprintf(
      '{x: new Date("%s"), o: %.2f, h: %.2f, l: %.2f, c: %.2f, v: %.0f, sma20: %s, sma50: %s, sma100: %s, sma200: %s}',
      format(row$date, "%Y-%m-%d"),
      row$open,
      row$high,
      row$low,
      row$close,
      row$volume,
      ifelse(is.na(row$sma20), "null", sprintf("%.2f", row$sma20)),
      ifelse(is.na(row$sma50), "null", sprintf("%.2f", row$sma50)),
      ifelse(is.na(row$sma100), "null", sprintf("%.2f", row$sma100)),
      ifelse(is.na(row$sma200), "null", sprintf("%.2f", row$sma200))
    )
    js_lines <- c(js_lines, js_line)
  }
  
  return(paste0("[\n                ", paste(js_lines, collapse = ",\n                "), "\n            ]"))
}

# Extract stock symbols from the dashboard JavaScript
# We'll need to parse the stocksData array to get symbols
cat("Parsing stock symbols from dashboard...\n")

# Find all stock symbols in the stocksData array
symbol_pattern <- 'symbol:\\s*"([^"]+)"'
symbol_matches <- regmatches(dashboard_text, gregexpr(symbol_pattern, dashboard_text, perl = TRUE))
symbols <- unique(gsub(symbol_pattern, "\\1", symbol_matches[[1]], perl = TRUE))

cat("Found", length(symbols), "unique stock symbols\n")

# Get chart data for each stock
cat("Generating chart data for stocks...\n")
chart_data_map <- list()
processed <- 0

for(symbol in symbols) {
  chart_data <- get_stock_chart_data(symbol, max_days = 200)
  if(!is.null(chart_data)) {
    chart_data_map[[symbol]] <- chart_data
    processed <- processed + 1
    if(processed %% 10 == 0) {
      cat("  Processed", processed, "stocks...\n")
    }
  }
}

cat("✅ Generated chart data for", processed, "stocks\n")

# Create JavaScript object with all chart data
cat("Creating JavaScript chart data object...\n")
chart_data_js <- "const stockChartData = {\n"
chart_data_lines <- c()

for(i in seq_along(chart_data_map)) {
  symbol <- names(chart_data_map)[i]
  chart_data <- chart_data_map[[symbol]]
  js_data <- chart_data_to_js(chart_data)
  chart_data_lines <- c(chart_data_lines, sprintf('    "%s": %s', symbol, js_data))
}

chart_data_js <- paste0(chart_data_js, paste(chart_data_lines, collapse = ",\n"), "\n};")

# Update the dashboard to use real chart data
cat("Updating dashboard with real chart data...\n")

# Replace the generateSampleChartData function to use real data
new_chart_function <- '
        function generateSampleChartData(symbol) {
            // Use real chart data if available
            if (stockChartData && stockChartData[symbol]) {
                return stockChartData[symbol];
            }
            
            // Fallback to sample data if real data not available
            const data = [];
            const basePrice = stocksData.find(s => s.symbol === symbol)?.currentPrice || 100;
            let currentPrice = basePrice;
            const startDate = new Date();
            startDate.setDate(startDate.getDate() - 200);
            
            for (let i = 0; i < 200; i++) {
                const date = new Date(startDate);
                date.setDate(date.getDate() + i);
                
                const change = (Math.random() - 0.5) * 0.05;
                const open = currentPrice;
                const close = open * (1 + change);
                const high = Math.max(open, close) * (1 + Math.random() * 0.02);
                const low = Math.min(open, close) * (1 - Math.random() * 0.02);
                const volume = Math.floor(Math.random() * 1000000) + 100000;
                
                data.push({
                    x: date,
                    o: open,
                    h: high,
                    l: low,
                    c: close,
                    v: volume
                });
                
                currentPrice = close;
            }
            
            return data;
        }'

# Find where to insert the chart data
# Insert after the stocksData definition
insertion_point <- regexpr("const stocksData = \\[[\\s\\S]*?\\];", dashboard_text, perl = TRUE)
if(insertion_point != -1) {
  insertion_end <- attr(insertion_point, "match.length") + insertion_point - 1
  
  # Insert chart data after stocksData
  new_dashboard <- paste0(
    substr(dashboard_text, 1, insertion_end),
    "\n\n        ",
    chart_data_js,
    "\n\n        ",
    new_chart_function,
    substr(dashboard_text, insertion_end + 1, nchar(dashboard_text))
  )
  
  # Update the generateSampleChartData function
  new_dashboard <- gsub(
    "function generateSampleChartData\\(symbol\\) \\{[^}]*\\}",
    new_chart_function,
    new_dashboard,
    perl = TRUE
  )
  
  # Save enhanced dashboard
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  enhanced_filename <- file.path(reports_dir, paste0("NSE_Interactive_Dashboard_with_Charts_", timestamp, ".html"))
  writeLines(new_dashboard, enhanced_filename)
  
  cat("✅ Enhanced dashboard saved to:", enhanced_filename, "\n")
  cat("📊 Chart data included for", length(chart_data_map), "stocks\n")
  
  # Also update the original dashboard
  writeLines(new_dashboard, latest_dashboard)
  cat("✅ Original dashboard updated with chart data\n")
  
} else {
  cat("⚠️ Could not find insertion point in dashboard\n")
}

cat("\n✅ Dashboard enhancement completed!\n")

