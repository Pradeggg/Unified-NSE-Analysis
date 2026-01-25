# MULTIPLE STOCK DAILY TECHNICAL ANALYSIS
# Extension of the daily technical analysis system for batch processing

# ===== MULTI-STOCK ANALYSIS FUNCTION =====
analyze_multiple_stocks <- function(symbols, output_file = NULL) {
  cat("🚀 Starting Multi-Stock Daily Technical Analysis\n")
  cat("Symbols:", paste(symbols, collapse = ", "), "\n")
  cat("=" , rep("=", 60), "\n", sep="")
  
  results <- list()
  summary_table <- data.frame(
    Symbol = character(),
    Technical_Score = numeric(),
    Current_Price = numeric(),
    Price_Change_Pct = numeric(),
    Trend_Score = numeric(),
    Momentum_Score = numeric(),
    Volume_Score = numeric(),
    Key_Signal = character(),
    stringsAsFactors = FALSE
  )
  
  for(symbol in symbols) {
    cat("\n📊 Analyzing", symbol, "...\n")
    
    # Analyze the stock
    result <- analyze_intraday_stock(symbol)
    
    if(!is.null(result)) {
      results[[symbol]] <- result
      
      # Determine key signal
      key_signal <- "NEUTRAL"
      if(result$technical_score >= 70) {
        key_signal <- "STRONG BUY"
      } else if(result$technical_score >= 60) {
        key_signal <- "BUY"
      } else if(result$technical_score >= 40) {
        key_signal <- "HOLD"
      } else if(result$technical_score >= 30) {
        key_signal <- "WEAK"
      } else {
        key_signal <- "AVOID"
      }
      
      # Add to summary table
      summary_table <- rbind(summary_table, data.frame(
        Symbol = symbol,
        Technical_Score = result$technical_score,
        Current_Price = round(result$current_price, 2),
        Price_Change_Pct = round(result$price_change_pct, 2),
        Trend_Score = round(result$score_components$trend, 1),
        Momentum_Score = round(result$score_components$momentum, 1),
        Volume_Score = round(result$score_components$volume, 1),
        Key_Signal = key_signal,
        stringsAsFactors = FALSE
      ))
    } else {
      cat("❌ Failed to analyze", symbol, "\n")
    }
    
    # Add small delay to avoid overwhelming the API
    Sys.sleep(1)
  }
  
  # Sort by technical score descending
  summary_table <- summary_table[order(summary_table$Technical_Score, decreasing = TRUE),]
  
  cat("\n" , rep("=", 60), "\n", sep="")
  cat("📈 MULTI-STOCK ANALYSIS SUMMARY\n")
  print(summary_table)
  
  # Generate comparative HTML report
  if(is.null(output_file)) {
    output_file <- paste0("Multi_Stock_Technical_Analysis_", 
                         format(Sys.time(), "%d%m%Y_%H%M"), ".html")
  }
  
  generate_multi_stock_html_report(results, summary_table, output_file)
  
  return(list(results = results, summary = summary_table, report_file = output_file))
}

# ===== MULTI-STOCK HTML REPORT GENERATION =====
generate_multi_stock_html_report <- function(results, summary_table, output_file) {
  cat("📄 Generating multi-stock HTML report...\n")
  
  # Create HTML content
  html_content <- sprintf('
<!DOCTYPE html>
<html>
<head>
    <title>Multi-Stock Daily Technical Analysis</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%); 
                 color: white; padding: 20px; border-radius: 10px; text-align: center; }
        .summary-table { margin: 20px 0; overflow-x: auto; }
        .summary-table table { width: 100%%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; }
        .summary-table th { background: #34495e; color: white; padding: 15px; text-align: left; }
        .summary-table td { padding: 12px 15px; border-bottom: 1px solid #ddd; }
        .summary-table tr:hover { background: #f8f9fa; }
        .score-excellent { color: #27ae60; font-weight: bold; }
        .score-good { color: #2ecc71; font-weight: bold; }
        .score-average { color: #f39c12; font-weight: bold; }
        .score-poor { color: #e74c3c; font-weight: bold; }
        .signal-strong-buy { background: #d5f4e6; color: #27ae60; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; }
        .signal-buy { background: #d6eaf8; color: #2980b9; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; }
        .signal-hold { background: #fef9e7; color: #f39c12; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; }
        .signal-weak { background: #fadbd8; color: #e74c3c; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; }
        .signal-avoid { background: #f2f3f4; color: #85929e; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; }
        .price-positive { color: #27ae60; }
        .price-negative { color: #e74c3c; }
        .individual-analysis { margin: 30px 0; }
        .stock-card { background: white; margin: 20px 0; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stock-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }
        .stock-score { font-size: 36px; font-weight: bold; }
        .component-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 15px 0; }
        .component-item { text-align: center; padding: 10px; background: #ecf0f1; border-radius: 8px; }
        .component-score { font-size: 24px; font-weight: bold; margin: 5px 0; }
        .signals-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin: 15px 0; }
        .signal-item { padding: 10px; border-radius: 8px; font-size: 14px; }
        .footer { text-align: center; margin-top: 30px; color: #7f8c8d; }
        .stats-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 32px; font-weight: bold; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 MULTI-STOCK DAILY TECHNICAL ANALYSIS</h1>
            <p>Comprehensive Technical Analysis Report | %s</p>
        </div>',
    format(Sys.time(), "%d %B %Y, %H:%M IST")
  )
  
  # Add summary statistics
  total_stocks <- nrow(summary_table)
  strong_buy <- sum(summary_table$Key_Signal == "STRONG BUY")
  buy_signals <- sum(summary_table$Key_Signal %in% c("STRONG BUY", "BUY"))
  avg_score <- round(mean(summary_table$Technical_Score), 1)
  top_performer <- summary_table$Symbol[1]
  
  html_content <- paste0(html_content, sprintf('
        <div class="stats-summary">
            <div class="stat-card">
                <h3>📈 Total Stocks Analyzed</h3>
                <div class="stat-number">%d</div>
            </div>
            <div class="stat-card">
                <h3>🚀 Strong Buy Signals</h3>
                <div class="stat-number score-excellent">%d</div>
            </div>
            <div class="stat-card">
                <h3>✅ Buy/Strong Buy</h3>
                <div class="stat-number score-good">%d</div>
            </div>
            <div class="stat-card">
                <h3>📊 Average Tech Score</h3>
                <div class="stat-number">%s</div>
            </div>
            <div class="stat-card">
                <h3>👑 Top Performer</h3>
                <div class="stat-number">%s</div>
            </div>
        </div>',
    total_stocks, strong_buy, buy_signals, avg_score, top_performer
  ))
  
  # Add summary table
  html_content <- paste0(html_content, '
        <div class="summary-table">
            <h2>📋 Summary Ranking</h2>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th><th>Symbol</th><th>Tech Score</th><th>Price</th><th>Change %</th>
                        <th>Trend</th><th>Momentum</th><th>Volume</th><th>Signal</th>
                    </tr>
                </thead>
                <tbody>')
  
  # Add table rows
  for(i in 1:nrow(summary_table)) {
    row <- summary_table[i,]
    
    score_class <- if(row$Technical_Score >= 70) "score-excellent"
                  else if(row$Technical_Score >= 60) "score-good"
                  else if(row$Technical_Score >= 40) "score-average"
                  else "score-poor"
    
    signal_class <- paste0("signal-", tolower(gsub(" ", "-", row$Key_Signal)))
    
    price_class <- if(row$Price_Change_Pct > 0) "price-positive" else "price-negative"
    
    html_content <- paste0(html_content, sprintf('
                    <tr>
                        <td><strong>%d</strong></td>
                        <td><strong>%s</strong></td>
                        <td><span class="%s">%s</span></td>
                        <td>₹%s</td>
                        <td><span class="%s">%s%%</span></td>
                        <td>%s</td>
                        <td>%s</td>
                        <td>%s</td>
                        <td><span class="%s">%s</span></td>
                    </tr>',
      i, row$Symbol, score_class, row$Technical_Score, row$Current_Price,
      price_class, ifelse(row$Price_Change_Pct > 0, "+", ""), row$Price_Change_Pct,
      row$Trend_Score, row$Momentum_Score, row$Volume_Score, 
      signal_class, row$Key_Signal
    ))
  }
  
  html_content <- paste0(html_content, '
                </tbody>
            </table>
        </div>')
  
  # Add individual analysis sections for top 5 stocks
  html_content <- paste0(html_content, '
        <div class="individual-analysis">
            <h2>🔍 Top 5 Detailed Analysis</h2>')
  
  top_5 <- head(summary_table, 5)
  for(i in 1:nrow(top_5)) {
    symbol <- top_5$Symbol[i]
    if(symbol %in% names(results)) {
      result <- results[[symbol]]
      
      score_class <- if(result$technical_score >= 70) "score-excellent"
                    else if(result$technical_score >= 60) "score-good"
                    else if(result$technical_score >= 40) "score-average"
                    else "score-poor"
      
      html_content <- paste0(html_content, sprintf('
            <div class="stock-card">
                <div class="stock-header">
                    <div>
                        <h3>%s</h3>
                        <p>Current Price: ₹%s | Change: %s%s (%%)</p>
                    </div>
                    <div class="stock-score %s">%s/100</div>
                </div>
                
                <div class="component-grid">
                    <div class="component-item">
                        <div>Trend</div>
                        <div class="component-score">%s</div>
                    </div>
                    <div class="component-item">
                        <div>Momentum</div>
                        <div class="component-score">%s</div>
                    </div>
                    <div class="component-item">
                        <div>Volume</div>
                        <div class="component-score">%s</div>
                    </div>
                    <div class="component-item">
                        <div>Support/Resist</div>
                        <div class="component-score">%s</div>
                    </div>
                    <div class="component-item">
                        <div>Volatility</div>
                        <div class="component-score">%s</div>
                    </div>
                </div>
                
                <div class="signals-grid">',
        symbol, round(result$current_price, 2), 
        ifelse(result$price_change_pct > 0, "+", ""), round(result$price_change_pct, 2),
        score_class, result$technical_score,
        round(result$score_components$trend, 1),
        round(result$score_components$momentum, 1), 
        round(result$score_components$volume, 1),
        round(result$score_components$support_resistance, 1),
        round(result$score_components$volatility, 1)
      ))
      
      # Add signals
      for(signal_name in names(result$signals)) {
        signal_text <- result$signals[[signal_name]]
        signal_class <- if(grepl("BUY|BULLISH|Above", signal_text, ignore.case = TRUE)) "signal-item" 
                      else if(grepl("SELL|BEARISH|Below", signal_text, ignore.case = TRUE)) "signal-item"
                      else "signal-item"
        
        html_content <- paste0(html_content, sprintf('
                    <div class="%s" style="background: #ecf0f1;">
                        <strong>%s:</strong> %s
                    </div>',
          signal_class,
          tools::toTitleCase(gsub("_signal", "", signal_name)),
          signal_text
        ))
      }
      
      html_content <- paste0(html_content, '
                </div>
            </div>')
    }
  }
  
  html_content <- paste0(html_content, '</div>')
  
  # Footer
  html_content <- paste0(html_content, '
        <div class="footer">
            <p>📊 Generated by Enhanced Multi-Stock Daily Technical Analysis System</p>
            <p>📈 Data Source: Yahoo Finance | Analysis Time: ', format(Sys.time(), "%d %B %Y, %H:%M IST"), '</p>
            <p>⚠️ This is for educational purposes only. Not financial advice.</p>
        </div>
    </div>
</body>
</html>')
  
  # Write to file
  writeLines(html_content, output_file)
  cat("✅ Multi-stock HTML report generated:", output_file, "\n")
  
  return(output_file)
}

# ===== PREDEFINED STOCK LISTS =====
nifty_50_sample <- c("RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR", 
                     "ICICIBANK", "KOTAKBANK", "LT", "ITC", "SBIN")

banking_stocks <- c("HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "AXISBANK")

it_stocks <- c("TCS", "INFY", "WIPRO", "HCLTECH", "TECHM")

pharma_stocks <- c("SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "BIOCON")

# ===== QUICK TEST FUNCTIONS =====
test_nifty_sample <- function() {
  cat("🚀 Testing with NIFTY 50 Sample Stocks\n")
  result <- analyze_multiple_stocks(nifty_50_sample)
  return(result)
}

test_banking_sector <- function() {
  cat("🏦 Testing Banking Sector Stocks\n")
  result <- analyze_multiple_stocks(banking_stocks)
  return(result)
}

test_it_sector <- function() {
  cat("💻 Testing IT Sector Stocks\n")
  result <- analyze_multiple_stocks(it_stocks)
  return(result)
}

cat("✅ Multi-Stock Analysis System Loaded\n")
cat("📊 Available functions:\n")
cat("   - analyze_multiple_stocks(symbols)\n")
cat("   - test_nifty_sample()\n")
cat("   - test_banking_sector()\n")
cat("   - test_it_sector()\n")
