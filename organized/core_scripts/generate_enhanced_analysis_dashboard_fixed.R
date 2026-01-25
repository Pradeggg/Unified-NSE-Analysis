# Enhanced Analysis Dashboard Generator - Fixed Version
# Multi-Timeframe & Price Action Analysis for NSE Stocks with Tabular Structure
# Author: AI Assistant
# Date: October 4, 2025

# Load required libraries
suppressMessages({
  library(DBI)
  library(RSQLite)
  library(dplyr)
  library(htmltools)
  library(jsonlite)
  library(lubridate)
})

# Set working directory
setwd("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis")

# Database connection
db_path <- "data/nse_analysis.db"
conn <- dbConnect(RSQLite::SQLite(), db_path)

# Get current date
analysis_date <- Sys.Date()

cat("🚀 Generating Enhanced Analysis Dashboard with Tabular Structure...\n")
cat("📅 Analysis Date:", as.character(analysis_date), "\n")

# Function to get stock data from database
get_stock_data <- function() {
  tryCatch({
    query <- "
    SELECT 
      symbol,
      current_price,
      change_1d,
      change_1w,
      change_1m,
      rsi,
      relative_strength,
      technical_score,
      can_slim_score,
      minervini_score,
      fundamental_score,
      trend_signal,
      trading_signal,
      market_cap_category
    FROM stocks_analysis 
    WHERE analysis_date = (
      SELECT MAX(analysis_date) FROM stocks_analysis
    )
    AND current_price > 10
    AND current_price < 20000
    ORDER BY technical_score DESC
    LIMIT 100
    "
    
    stocks_data <- dbGetQuery(conn, query)
    
    # Apply filters
    if (nrow(stocks_data) > 0) {
      stocks_data <- stocks_data %>%
        filter(
          abs(change_1d) < 15,
          abs(change_1w) < 40,
          current_price >= 25,
          current_price <= 5000,
          rsi >= 25,
          rsi <= 75,
          technical_score >= 35,
          technical_score <= 95
        )
    }
    
    return(stocks_data)
  }, error = function(e) {
    cat("❌ Error fetching stock data:", e$message, "\n")
    return(data.frame())
  })
}

# Function to generate tabular data
generate_tabular_data <- function(stocks_data) {
  cat("📊 Generating Tabular Data...\n")
  
  # 1. Daily Bullish Patterns Table
  daily_bullish_table <- stocks_data %>%
    filter(!is.na(change_1d), change_1d > 0) %>%
    mutate(
      momentum = change_1d,
      pattern = case_when(
        change_1d > 15 ~ "Strong Breakout",
        change_1d > 10 ~ "Bullish Flag", 
        change_1d > 5 ~ "Ascending Triangle",
        TRUE ~ "Bullish Pennant"
      ),
      rsi_status = case_when(
        rsi > 70 ~ "Overbought",
        rsi < 30 ~ "Oversold",
        TRUE ~ "Normal"
      )
    ) %>%
    arrange(desc(change_1d)) %>%
    select(symbol, current_price, momentum, rsi, rsi_status, pattern, relative_strength, technical_score, market_cap_category)
  
  # 2. Weekly Bullish Patterns Table
  weekly_bullish_table <- stocks_data %>%
    filter(!is.na(change_1w), change_1w > 0) %>%
    mutate(
      momentum = change_1w,
      pattern = case_when(
        change_1w > 30 ~ "Strong Uptrend",
        change_1w > 15 ~ "Momentum Breakout",
        change_1w > 8 ~ "Bullish Channel",
        TRUE ~ "Support Bounce"
      ),
      rsi_status = case_when(
        rsi > 70 ~ "Overbought",
        rsi < 30 ~ "Oversold", 
        TRUE ~ "Normal"
      )
    ) %>%
    arrange(desc(change_1w)) %>%
    select(symbol, current_price, momentum, rsi, rsi_status, pattern, relative_strength, technical_score, market_cap_category)
  
  # 3. Relative Strength Leaders Table
  rs_leaders_table <- stocks_data %>%
    filter(!is.na(relative_strength)) %>%
    mutate(
      rs_category = case_when(
        relative_strength > 50 ~ "Exceptional",
        relative_strength > 20 ~ "Very Strong",
        relative_strength > 10 ~ "Strong",
        relative_strength > 5 ~ "Moderate",
        TRUE ~ "Weak"
      ),
      rs_strength = case_when(
        relative_strength > 20 ~ "Strong",
        relative_strength > 10 ~ "Medium",
        TRUE ~ "Weak"
      )
    ) %>%
    arrange(desc(relative_strength)) %>%
    select(symbol, current_price, relative_strength, rs_category, rs_strength, technical_score, rsi, change_1d, change_1w, market_cap_category)
  
  # 4. Top Technical Scores Table
  top_technical_table <- stocks_data %>%
    filter(!is.na(technical_score)) %>%
    mutate(
      risk_level = case_when(
        rsi > 70 | rsi < 30 ~ "High",
        rsi > 60 | rsi < 40 ~ "Medium",
        TRUE ~ "Low"
      ),
      investment_horizon = case_when(
        technical_score > 75 & relative_strength > 1.5 ~ "Short-term (1-3 months)",
        technical_score > 60 & relative_strength > 1.2 ~ "Medium-term (3-6 months)",
        technical_score > 45 & relative_strength > 1.0 ~ "Long-term (6+ months)",
        TRUE ~ "Watch List"
      )
    ) %>%
    arrange(desc(technical_score)) %>%
    select(symbol, current_price, technical_score, relative_strength, rsi, risk_level, investment_horizon, change_1d, change_1w, market_cap_category)
  
  # 5. Market Cap Analysis Table
  market_cap_analysis <- stocks_data %>%
    filter(!is.na(relative_strength)) %>%
    group_by(market_cap_category) %>%
    summarise(
      stock_count = n(),
      avg_technical_score = round(mean(technical_score, na.rm = TRUE), 2),
      avg_relative_strength = round(mean(relative_strength, na.rm = TRUE), 2),
      avg_rsi = round(mean(rsi, na.rm = TRUE), 2),
      avg_change_1d = round(mean(change_1d, na.rm = TRUE), 2),
      avg_change_1w = round(mean(change_1w, na.rm = TRUE), 2),
      .groups = 'drop'
    ) %>%
    mutate(
      recommendation = case_when(
        avg_relative_strength > 1.3 & avg_technical_score > 60 ~ "Strong Buy",
        avg_relative_strength > 1.1 & avg_technical_score > 50 ~ "Buy",
        avg_relative_strength > 0.9 & avg_technical_score > 40 ~ "Hold",
        TRUE ~ "Avoid"
      )
    ) %>%
    arrange(desc(avg_technical_score))
  
  # 6. Risk Management Table
  risk_management_table <- stocks_data %>%
    filter(!is.na(technical_score), !is.na(rsi)) %>%
    mutate(
      risk_category = case_when(
        technical_score > 70 & rsi > 50 & rsi < 70 ~ "Low Risk",
        technical_score > 50 & rsi > 40 & rsi < 80 ~ "Medium Risk",
        TRUE ~ "High Risk"
      )
    ) %>%
    group_by(risk_category) %>%
    summarise(
      stock_count = n(),
      avg_technical_score = round(mean(technical_score, na.rm = TRUE), 2),
      avg_relative_strength = round(mean(relative_strength, na.rm = TRUE), 2),
      avg_rsi = round(mean(rsi, na.rm = TRUE), 2),
      .groups = 'drop'
    ) %>%
    arrange(desc(avg_technical_score))
  
  return(list(
    dailyBullish = daily_bullish_table,
    weeklyBullish = weekly_bullish_table,
    rsLeaders = rs_leaders_table,
    topTechnical = top_technical_table,
    marketCapAnalysis = market_cap_analysis,
    riskManagement = risk_management_table
  ))
}

# Function to generate HTML with proper tabular structure
generate_html_dashboard <- function(tabular_data) {
  cat("🎨 Generating HTML Dashboard with Tabular Structure...\n")
  
  # Convert data to JSON for JavaScript
  tabular_json <- toJSON(tabular_data, auto_unbox = TRUE)
  
  html_content <- paste0('
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Enhanced Analysis Dashboard - Tabular View</title>
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
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #f8fafc;
            color: #1f2937;
            line-height: 1.6;
            font-size: 14px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 32px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
            border: 1px solid #e5e7eb;
        }

        .header h1 {
            font-size: 1.875rem;
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 8px;
        }

        .header p {
            color: #6b7280;
            font-size: 0.95rem;
        }

        .section-header {
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 2px solid #e5e7eb;
        }

        .section-header h2 {
            font-size: 1.5rem;
            font-weight: 600;
            color: #1f2937;
            margin: 0;
        }

        .analysis-section {
            margin: 32px 0;
        }

        .timeframe-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .timeframe-card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border: 1px solid #e5e7eb;
            transition: all 0.2s ease;
        }

        .timeframe-card:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }

        .timeframe-header {
            margin-bottom: 16px;
        }

        .timeframe-header h3 {
            font-size: 1.125rem;
            font-weight: 600;
            color: #1f2937;
            margin: 0 0 4px 0;
        }

        .timeframe-header p {
            font-size: 0.875rem;
            color: #6b7280;
            margin: 0;
        }

        .export-buttons {
            display: flex;
            gap: 8px;
            margin-top: 16px;
        }

        .export-btn {
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .export-btn:hover {
            background: #1d4ed8;
            transform: translateY(-1px);
        }

        .csv-btn {
            background: #10b981;
        }

        .csv-btn:hover {
            background: #059669;
        }

        .excel-btn {
            background: #059669;
        }

        .excel-btn:hover {
            background: #047857;
        }

        .tradingview-btn {
            background: #06b6d4;
        }

        .tradingview-btn:hover {
            background: #0891b2;
        }

        /* Table Styles */
        .table-container {
            overflow-x: auto;
            margin: 1rem 0;
        }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .data-table th {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .data-table td {
            padding: 10px 8px;
            border-bottom: 1px solid #e5e7eb;
            font-size: 0.9rem;
        }

        .data-table tr:hover {
            background-color: #f8fafc;
        }

        .data-table tr:nth-child(even) {
            background-color: #f9fafb;
        }

        .data-table tr:nth-child(even):hover {
            background-color: #f1f5f9;
        }

        /* Cell styling based on data */
        .data-table td.positive {
            color: #059669;
            font-weight: 600;
        }

        .data-table td.negative {
            color: #dc2626;
            font-weight: 600;
        }

        .data-table td.strong {
            color: #059669;
            font-weight: 700;
        }

        .data-table td.medium {
            color: #d97706;
            font-weight: 600;
        }

        .data-table td.weak {
            color: #dc2626;
            font-weight: 500;
        }

        .data-table td.overbought {
            color: #dc2626;
            font-weight: 600;
            background-color: rgba(220, 38, 38, 0.1);
        }

        .data-table td.oversold {
            color: #059669;
            font-weight: 600;
            background-color: rgba(5, 150, 105, 0.1);
        }

        .data-table td.normal {
            color: #6b7280;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #6b7280;
            font-style: italic;
        }

        .no-data {
            text-align: center;
            padding: 40px;
            color: #9ca3af;
            font-style: italic;
        }

        @media (max-width: 768px) {
            .container {
                padding: 16px;
            }

            .timeframe-grid {
                grid-template-columns: 1fr;
            }

            .data-table {
                font-size: 0.8rem;
            }

            .data-table th,
            .data-table td {
                padding: 8px 4px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NSE Enhanced Analysis Dashboard</h1>
            <p>Comprehensive Tabular Analysis with Export Functionality</p>
            <p>Analysis Date: ', as.character(analysis_date), '</p>
        </div>
        
        <!-- Tabular Data Section -->
        <div class="analysis-section">
            <div class="section-header">
                <h2>📊 Tabular Data Analysis</h2>
                <p>Comprehensive tabular view of all analysis with enhanced export functionality</p>
            </div>
            
            <div class="timeframe-grid">
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📈 Daily Bullish Patterns Table</h3>
                        <p>Complete table of daily bullish momentum stocks</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="dailyBullishTableContent">
                        <div class="loading">Loading daily bullish patterns table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>📅 Weekly Bullish Patterns Table</h3>
                        <p>Complete table of weekly bullish momentum stocks</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="weeklyBullishTableContent">
                        <div class="loading">Loading weekly bullish patterns table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>💪 Relative Strength Leaders Table</h3>
                        <p>Complete table of relative strength leaders</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="rsLeadersTableContent">
                        <div class="loading">Loading relative strength leaders table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🏆 Top Technical Scores Table</h3>
                        <p>Complete table of top technical scoring stocks</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                            <button class="export-btn tradingview-btn">📈 TradingView</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="topTechnicalTableContent">
                        <div class="loading">Loading top technical scores table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🏢 Market Cap Analysis Table</h3>
                        <p>Market cap category performance analysis</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="marketCapTableContent">
                        <div class="loading">Loading market cap analysis table...</div>
                    </div>
                </div>
                
                <div class="timeframe-card">
                    <div class="timeframe-header">
                        <h3>🛡️ Risk Management Table</h3>
                        <p>Risk categorization and management analysis</p>
                        <div class="export-buttons">
                            <button class="export-btn csv-btn">📊 CSV Export</button>
                            <button class="export-btn excel-btn">📈 Excel Export</button>
                        </div>
                    </div>
                    <div class="timeframe-content" id="riskManagementTableContent">
                        <div class="loading">Loading risk management table...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Tabular Data
        const tabularData = ', tabular_json, ';

        // Tabular Display Functions
        function populateTabularData() {
            populateTabularTable("dailyBullishTableContent", tabularData.dailyBullish, "Daily Bullish Patterns");
            populateTabularTable("weeklyBullishTableContent", tabularData.weeklyBullish, "Weekly Bullish Patterns");
            populateTabularTable("rsLeadersTableContent", tabularData.rsLeaders, "Relative Strength Leaders");
            populateTabularTable("topTechnicalTableContent", tabularData.topTechnical, "Top Technical Scores");
            populateTabularTable("marketCapTableContent", tabularData.marketCapAnalysis, "Market Cap Analysis");
            populateTabularTable("riskManagementTableContent", tabularData.riskManagement, "Risk Management");
        }
        
        function populateTabularTable(containerId, data, title) {
            const container = document.getElementById(containerId);
            
            if (!data || data.length === 0) {
                container.innerHTML = "<div class=\\"no-data\\">No data available for " + title + "</div>";
                return;
            }
            
            let html = "<div class=\\"table-container\\">";
            html += "<table class=\\"data-table\\">";
            html += "<thead><tr>";
            
            // Create table headers based on data structure
            if (data.length > 0) {
                const headers = Object.keys(data[0]);
                headers.forEach(header => {
                    html += "<th>" + header.replace(/_/g, " ").toUpperCase() + "</th>";
                });
            }
            
            html += "</tr></thead><tbody>";
            
            // Add data rows
            data.forEach(row => {
                html += "<tr>";
                Object.values(row).forEach(value => {
                    const cellClass = getCellClass(value, Object.keys(row)[Object.values(row).indexOf(value)]);
                    html += "<td class=\\"" + cellClass + "\\">" + formatCellValue(value) + "</td>";
                });
                html += "</tr>";
            });
            
            html += "</tbody></table>";
            html += "</div>";
            
            container.innerHTML = html;
        }
        
        function getCellClass(value, columnName) {
            if (columnName.includes("rsi") || columnName.includes("RSI")) {
                if (value > 70) return "overbought";
                if (value < 30) return "oversold";
                return "normal";
            }
            if (columnName.includes("change") || columnName.includes("momentum")) {
                return value >= 0 ? "positive" : "negative";
            }
            if (columnName.includes("relative_strength") || columnName.includes("technical_score")) {
                if (value > 20) return "strong";
                if (value > 10) return "medium";
                return "weak";
            }
            return "";
        }
        
        function formatCellValue(value) {
            if (typeof value === "number") {
                if (value % 1 !== 0) {
                    return value.toFixed(2);
                }
                return value.toString();
            }
            return value;
        }

        // Export Functions
        function exportTableToCSV(tableType) {
            let data = [];
            let filename = "";
            
            switch(tableType) {
                case "dailyBullishTable":
                    data = tabularData.dailyBullish;
                    filename = "NSE_Daily_Bullish_Patterns.csv";
                    break;
                case "weeklyBullishTable":
                    data = tabularData.weeklyBullish;
                    filename = "NSE_Weekly_Bullish_Patterns.csv";
                    break;
                case "rsLeadersTable":
                    data = tabularData.rsLeaders;
                    filename = "NSE_Relative_Strength_Leaders.csv";
                    break;
                case "topTechnicalTable":
                    data = tabularData.topTechnical;
                    filename = "NSE_Top_Technical_Scores.csv";
                    break;
                case "marketCapTable":
                    data = tabularData.marketCapAnalysis;
                    filename = "NSE_Market_Cap_Analysis.csv";
                    break;
                case "riskManagementTable":
                    data = tabularData.riskManagement;
                    filename = "NSE_Risk_Management.csv";
                    break;
            }
            
            if (!data || data.length === 0) {
                alert("No data available for export");
                return;
            }
            
            let csvContent = "";
            if (data.length > 0) {
                const headers = Object.keys(data[0]);
                csvContent = headers.join(",") + "\\n";
                data.forEach(row => {
                    const values = Object.values(row).map(value => 
                        typeof value === "string" && value.includes(",") ? "\\"" + value + "\\"" : value
                    );
                    csvContent += values.join(",") + "\\n";
                });
            }
            
            downloadCSV(csvContent, filename);
        }
        
        function downloadCSV(content, filename) {
            const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
            const link = document.createElement("a");
            const url = URL.createObjectURL(blob);
            link.setAttribute("href", url);
            link.setAttribute("download", filename);
            link.style.visibility = "hidden";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
        
        // Initialize everything when page loads
        document.addEventListener("DOMContentLoaded", () => {
            populateTabularData();
        });
    </script>
</body>
</html>')
  
  return(html_content)
}

# Main execution
tryCatch({
  cat("📊 Starting Enhanced Analysis Dashboard Generation...\n")
  
  # Get stock data
  stocks_data <- get_stock_data()
  
  if (nrow(stocks_data) == 0) {
    cat("❌ No stock data found in database\n")
    stop("No data available")
  }
  
  cat("✅ Found", nrow(stocks_data), "stocks in database\n")
  
  # Generate tabular data
  tabular_data <- generate_tabular_data(stocks_data)
  
  # Generate HTML dashboard
  html_content <- generate_html_dashboard(tabular_data)
  
  # Save HTML file
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  filename <- paste0("reports/NSE_Enhanced_Analysis_Dashboard_Tabular_", timestamp, ".html")
  
  writeLines(html_content, filename)
  
  cat("✅ Enhanced Analysis Dashboard with Tabular Structure generated successfully!\n")
  cat("📁 File saved:", filename, "\n")
  cat("🌐 Opening dashboard in browser...\n")
  
  # Open the dashboard
  system(paste("open", filename))
  
}, error = function(e) {
  cat("❌ Error generating dashboard:", e$message, "\n")
}, finally = {
  # Close database connection
  if (exists("conn")) {
    dbDisconnect(conn)
  }
})

cat("🎉 Enhanced Analysis Dashboard with Tabular Structure generation completed!\n")

