#!/usr/bin/env Rscript
# Analyze stocks in Defence, Realty, and Infrastructure sectors

library(dplyr)

cat("=== ANALYZING STOCKS IN DEFENCE, REALTY & INFRA SECTORS ===\n\n")

# Load latest analysis results
latest_file <- list.files("reports", pattern = "comprehensive_nse_enhanced_.*\\.csv", full.names = TRUE)
if(length(latest_file) > 0) {
  latest_file <- latest_file[order(file.info(latest_file)$mtime, decreasing = TRUE)][1]
  cat("Loading analysis results from:", basename(latest_file), "\n\n")
  
  analysis_results <- read.csv(latest_file, stringsAsFactors = FALSE)
  cat("Total stocks analyzed:", nrow(analysis_results), "\n\n")
  
  # Get all unique symbols
  all_symbols <- unique(analysis_results$SYMBOL)
  
  # Search for defence-related stocks (common symbols)
  cat("Searching for DEFENCE stocks...\n")
  defence_pattern <- grep("HAL|BEL|BEML|MIDHANI|DEFENCE|DEFENSE|AERO|MISHRA|GARDEN|COCHIN|MAZAGON|ASTRA|BHARATFORG", all_symbols, ignore.case = TRUE, value = TRUE)
  cat("Found:", length(defence_pattern), "potential defence stocks\n")
  if(length(defence_pattern) > 0) {
    print(defence_pattern)
  }
  
  # Search for realty stocks
  cat("\nSearching for REALTY stocks...\n")
  realty_pattern <- grep("DLF|GODREJPROP|OBEROIRLTY|PRESTIGE|SOBHA|BRIGADE|MAHINDRA|PURAVANKARA|KOLTEPATIL|LODHA|MACROTECH|SUNTECK|RAHEJA|INDIAHOUSING", all_symbols, ignore.case = TRUE, value = TRUE)
  cat("Found:", length(realty_pattern), "potential realty stocks\n")
  if(length(realty_pattern) > 0) {
    print(realty_pattern)
  }
  
  # Search for infrastructure stocks
  cat("\nSearching for INFRASTRUCTURE stocks...\n")
  infra_pattern <- grep("LARSEN|^LT$|BHEL|SIEMENS|ABB|THERMAX|ADANIPORTS|CONCOR|GMRINFRA|IRBINFRA|RELINFRA|HCC|POWERGRID|NTPC|ADANIPOWER|ADANIGREEN|ADANITRANS", all_symbols, ignore.case = TRUE, value = TRUE)
  cat("Found:", length(infra_pattern), "potential infrastructure stocks\n")
  if(length(infra_pattern) > 0) {
    print(infra_pattern)
  }
  
  # Filter and rank by technical strength
  cat("\n\n")
  cat("═══════════════════════════════════════════════════════════════\n")
  cat("DEFENCE SECTOR - TOP STOCKS BY TECHNICAL STRENGTH\n")
  cat("═══════════════════════════════════════════════════════════════\n")
  
  if(length(defence_pattern) > 0) {
    defence_analysis <- analysis_results %>%
      filter(SYMBOL %in% defence_pattern) %>%
      arrange(desc(TECHNICAL_SCORE)) %>%
      select(SYMBOL, MARKET_CAP_CATEGORY, CURRENT_PRICE, CHANGE_1D, CHANGE_1W, CHANGE_1M, 
             TECHNICAL_SCORE, RELATIVE_STRENGTH, TRADING_SIGNAL, TREND_SIGNAL)
    
    print(defence_analysis)
    cat("\nTop 5 Defence Stocks:\n")
    print(head(defence_analysis, 5))
  } else {
    cat("No defence stocks found in analysis results.\n")
  }
  
  cat("\n═══════════════════════════════════════════════════════════════\n")
  cat("REALTY SECTOR - TOP STOCKS BY TECHNICAL STRENGTH\n")
  cat("═══════════════════════════════════════════════════════════════\n")
  
  if(length(realty_pattern) > 0) {
    realty_analysis <- analysis_results %>%
      filter(SYMBOL %in% realty_pattern) %>%
      arrange(desc(TECHNICAL_SCORE)) %>%
      select(SYMBOL, MARKET_CAP_CATEGORY, CURRENT_PRICE, CHANGE_1D, CHANGE_1W, CHANGE_1M,
             TECHNICAL_SCORE, RELATIVE_STRENGTH, TRADING_SIGNAL, TREND_SIGNAL)
    
    print(realty_analysis)
    cat("\nTop 5 Realty Stocks:\n")
    print(head(realty_analysis, 5))
  } else {
    cat("No realty stocks found in analysis results.\n")
  }
  
  cat("\n═══════════════════════════════════════════════════════════════\n")
  cat("INFRASTRUCTURE SECTOR - TOP STOCKS BY TECHNICAL STRENGTH\n")
  cat("═══════════════════════════════════════════════════════════════\n")
  
  if(length(infra_pattern) > 0) {
    infra_analysis <- analysis_results %>%
      filter(SYMBOL %in% infra_pattern) %>%
      arrange(desc(TECHNICAL_SCORE)) %>%
      select(SYMBOL, MARKET_CAP_CATEGORY, CURRENT_PRICE, CHANGE_1D, CHANGE_1W, CHANGE_1M,
             TECHNICAL_SCORE, RELATIVE_STRENGTH, TRADING_SIGNAL, TREND_SIGNAL)
    
    print(infra_analysis)
    cat("\nTop 5 Infrastructure Stocks:\n")
    print(head(infra_analysis, 5))
  } else {
    cat("No infrastructure stocks found in analysis results.\n")
  }
  
  # Save results to CSV
  output_file <- "reports/top_sector_stocks_analysis.csv"
  
  all_sector_results <- data.frame()
  
  if(length(defence_pattern) > 0 && exists("defence_analysis")) {
    defence_analysis$SECTOR <- "DEFENCE"
    all_sector_results <- rbind(all_sector_results, defence_analysis)
  }
  
  if(length(realty_pattern) > 0 && exists("realty_analysis")) {
    realty_analysis$SECTOR <- "REALTY"
    all_sector_results <- rbind(all_sector_results, realty_analysis)
  }
  
  if(length(infra_pattern) > 0 && exists("infra_analysis")) {
    infra_analysis$SECTOR <- "INFRASTRUCTURE"
    all_sector_results <- rbind(all_sector_results, infra_analysis)
  }
  
  if(nrow(all_sector_results) > 0) {
    write.csv(all_sector_results, output_file, row.names = FALSE)
    cat("\n✅ Results saved to:", output_file, "\n")
    
    # Ensure data frames are created even if empty
    if(!exists("defence_analysis")) defence_analysis <- data.frame()
    if(!exists("realty_analysis")) realty_analysis <- data.frame()
    if(!exists("infra_analysis")) infra_analysis <- data.frame()
    
    # Generate HTML report matching Long Term Screeners format
    generate_html_report <- function(defence_df, realty_df, infra_df, output_dir = "reports") {
      timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
      html_file <- file.path(output_dir, paste0("Sector_Analysis_Report_", timestamp, ".html"))
      
      # Helper function to format sector stock list
      format_sector_list <- function(df, sector_name) {
        if(nrow(df) == 0) {
          return('<div class="no-data">No ', sector_name, ' stocks found in analysis.</div>')
        }
        
        html <- '<div class="screener-list">'
        for(i in 1:nrow(df)) {
          row <- df[i, ]
          signal_color <- switch(row$TRADING_SIGNAL,
                                "STRONG_BUY" = "#28a745",
                                "BUY" = "#5cb85c",
                                "HOLD" = "#ffc107",
                                "WEAK_HOLD" = "#ff9800",
                                "SELL" = "#dc3545",
                                "#6c757d")
          
          html <- paste0(html, '<div class="screener-item">
            <div class="stock-info">
                <span class="stock-symbol">', row$SYMBOL, '</span>
                <span class="stock-price">₹', sprintf("%.2f", row$CURRENT_PRICE), ' | ', row$MARKET_CAP_CATEGORY, '</span>
            </div>
            <div class="metric-value score">', sprintf("%.1f", row$TECHNICAL_SCORE), '</div>
            <div class="metric-value" style="background: ', signal_color, '; color: white;">', row$TRADING_SIGNAL, '</div>
          </div>')
        }
        html <- paste0(html, '</div>')
        return(html)
      }
      
      # Get analysis date
      analysis_date <- format(Sys.Date(), "%B %d, %Y")
      
      html_content <- paste0('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sector Analysis Report - Defence, Realty & Infrastructure</title>
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
        }

        .container {
            max-width: 100%;
            margin: 0 auto;
            padding: 20px;
            width: 100%;
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
            opacity: 0.9;
        }

        .sector-section {
            margin: 2rem 0;
            padding: 2rem;
            background: #f8f9fa;
            border-radius: 12px;
        }

        .section-header {
            margin-bottom: 1.5rem;
        }

        .section-header h2 {
            font-size: 2rem;
            font-weight: 400;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }

        .section-header p {
            color: #7f8c8d;
            font-size: 1rem;
        }

        .screeners-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-top: 1.5rem;
        }

        .screener-card {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .screener-header h3 {
            color: #2c3e50;
            margin-bottom: 0.5rem;
            font-size: 1.2rem;
            font-weight: 500;
        }

        .screener-header p {
            color: #7f8c8d;
            font-size: 0.9rem;
        }

        .screener-list {
            margin-top: 1rem;
        }

        .screener-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid #ecf0f1;
            cursor: pointer;
            transition: background-color 0.2s;
        }

        .screener-item:hover {
            background-color: #f8f9fa;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
            margin-left: -0.5rem;
            margin-right: -0.5rem;
            border-radius: 4px;
        }

        .screener-item:last-child {
            border-bottom: none;
        }

        .stock-info {
            display: flex;
            flex-direction: column;
            flex: 1;
        }

        .stock-symbol {
            font-weight: 600;
            color: #2c3e50;
            font-size: 1rem;
        }

        .stock-price {
            font-size: 0.85rem;
            color: #7f8c8d;
            margin-top: 0.25rem;
        }

        .metric-value {
            font-weight: 600;
            padding: 0.35rem 0.75rem;
            border-radius: 4px;
            font-size: 0.9rem;
            margin-left: 0.5rem;
        }

        .metric-value.rs {
            background: #e8f5e8;
            color: #27ae60;
        }

        .metric-value.score {
            background: #e3f2fd;
            color: #1976d2;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .summary-card {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }

        .summary-card h3 {
            color: #667eea;
            margin-bottom: 0.75rem;
            font-size: 1.1rem;
            font-weight: 500;
        }

        .summary-card .number {
            font-size: 2.5rem;
            font-weight: 300;
            color: #764ba2;
            margin: 0.5rem 0;
        }

        .summary-card .score {
            font-size: 1.1rem;
            color: #27ae60;
            margin-top: 0.5rem;
            font-weight: 500;
        }

        .table-section {
            margin-top: 2rem;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            background: #667eea;
            color: white;
            padding: 1rem;
            text-align: left;
            font-weight: 500;
            font-size: 0.9rem;
        }

        td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #ecf0f1;
            font-size: 0.9rem;
        }

        tr:hover {
            background-color: #f8f9fa;
        }

        .no-data {
            text-align: center;
            color: #7f8c8d;
            font-style: italic;
            padding: 2rem;
        }

        @media (max-width: 768px) {
            .screeners-grid {
                grid-template-columns: 1fr;
            }

            .summary-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Sector Analysis Report</h1>
            <p>Defence, Realty & Infrastructure Stocks</p>
            <p style="margin-top: 10px; font-size: 1rem; opacity: 0.8;">Analysis Date: ', analysis_date, '</p>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <h3>🛡️ Defence Sector</h3>
                <div class="number">', ifelse(nrow(defence_df) > 0, nrow(defence_df), 0), '</div>
                <p>Stocks Analyzed</p>
                ', ifelse(nrow(defence_df) > 0, paste0('<p class="score">Top Score: ', sprintf("%.1f", max(defence_df$TECHNICAL_SCORE)), '</p>'), '<p class="score">N/A</p>'), '
            </div>
            <div class="summary-card">
                <h3>🏢 Realty Sector</h3>
                <div class="number">', ifelse(nrow(realty_df) > 0, nrow(realty_df), 0), '</div>
                <p>Stocks Analyzed</p>
                ', ifelse(nrow(realty_df) > 0, paste0('<p class="score">Top Score: ', sprintf("%.1f", max(realty_df$TECHNICAL_SCORE)), '</p>'), '<p class="score">N/A</p>'), '
            </div>
            <div class="summary-card">
                <h3>🏗️ Infrastructure Sector</h3>
                <div class="number">', ifelse(nrow(infra_df) > 0, nrow(infra_df), 0), '</div>
                <p>Stocks Analyzed</p>
                ', ifelse(nrow(infra_df) > 0, paste0('<p class="score">Top Score: ', sprintf("%.1f", max(infra_df$TECHNICAL_SCORE)), '</p>'), '<p class="score">N/A</p>'), '
            </div>
        </div>

        <div class="sector-section">
            <div class="section-header">
                <h2>🛡️ DEFENCE SECTOR</h2>
                <p>Top stocks by technical strength in Defence & Aerospace</p>
            </div>
            <div class="screeners-grid">
                <div class="screener-card">
                    <div class="screener-header">
                        <h3>💪 Top Defence Stocks</h3>
                        <p>Ranked by Technical Score</p>
                    </div>
                    ', format_sector_list(defence_df, "Defence"), '
                </div>
            </div>
        </div>

        <div class="sector-section">
            <div class="section-header">
                <h2>🏢 REALTY SECTOR</h2>
                <p>Top stocks by technical strength in Real Estate</p>
            </div>
            <div class="screeners-grid">
                <div class="screener-card">
                    <div class="screener-header">
                        <h3>💪 Top Realty Stocks</h3>
                        <p>Ranked by Technical Score</p>
                    </div>
                    ', format_sector_list(realty_df, "Realty"), '
                </div>
            </div>
        </div>

        <div class="sector-section">
            <div class="section-header">
                <h2>🏗️ INFRASTRUCTURE SECTOR</h2>
                <p>Top stocks by technical strength in Infrastructure</p>
            </div>
            <div class="screeners-grid">
                <div class="screener-card">
                    <div class="screener-header">
                        <h3>💪 Top Infrastructure Stocks</h3>
                        <p>Ranked by Technical Score</p>
                    </div>
                    ', format_sector_list(infra_df, "Infrastructure"), '
                </div>
            </div>
        </div>
    </div>
</body>
</html>')
      
      writeLines(html_content, html_file)
      return(html_file)
    }
    
    html_file <- generate_html_report(defence_analysis, realty_analysis, infra_analysis)
    
    cat("✅ HTML report saved to:", html_file, "\n")
  }
  
} else {
  cat("❌ No analysis results found\n")
}

