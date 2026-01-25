# Enhanced Dashboard Generator with TradingView-like Charts
# This script generates an enhanced HTML dashboard with candlestick charts

library(dplyr)
library(RSQLite)
library(DBI)
library(jsonlite)
library(zoo)
library(TTR)

# Load the analysis results
load_analysis_data <- function() {
  # Load the comprehensive analysis results - try multiple possible files
  possible_files <- c(
    "../../reports/comprehensive_nse_enhanced_24092025_20250924_190611.csv",
    "../../reports/comprehensive_nse_enhanced_23092025_20250924_015720.csv",
    "../../reports/comprehensive_nse_enhanced_22092025_20250923_203311.csv"
  )
  
  for (csv_file in possible_files) {
    if (file.exists(csv_file)) {
      cat("Loading analysis data from:", csv_file, "\n")
      return(read.csv(csv_file, stringsAsFactors = FALSE))
    }
  }
  
  stop("Analysis results file not found. Please run the analysis first.")
}

# Load historical stock data for charting
load_historical_data <- function(symbol, days = 200) {
  # Load from the main NSE data
  nse_data_file <- "../../data/nse_stock_cache.RData"
  if (file.exists(nse_data_file)) {
    load(nse_data_file)
    if (exists("nse_stock_data")) {
      stock_data <- nse_stock_data %>%
        filter(SYMBOL == symbol) %>%
        arrange(TIMESTAMP) %>%
        tail(days) %>%
        select(TIMESTAMP, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY) %>%
        mutate(
          TIMESTAMP = as.Date(TIMESTAMP),
          VOLUME = TOTTRDQTY
        ) %>%
        select(-TOTTRDQTY)
      
      # Calculate moving averages
      stock_data <- stock_data %>%
        mutate(
          SMA_20 = zoo::rollmean(CLOSE, k = 20, fill = NA, align = "right"),
          SMA_50 = zoo::rollmean(CLOSE, k = 50, fill = NA, align = "right"),
          SMA_200 = zoo::rollmean(CLOSE, k = 200, fill = NA, align = "right"),
          EMA_12 = TTR::EMA(CLOSE, n = 12),
          EMA_26 = TTR::EMA(CLOSE, n = 26)
        )
      
      return(stock_data)
    }
  }
  return(NULL)
}

# Generate enhanced HTML dashboard
generate_enhanced_dashboard <- function() {
  cat("Generating enhanced dashboard with TradingView-like charts...\n")
  
  # Load analysis data
  analysis_data <- load_analysis_data()
  
  # Convert to JavaScript format
  stocks_data <- analysis_data %>%
    mutate(
      companyName = ifelse(is.na(COMPANY_NAME) | COMPANY_NAME == "", SYMBOL, COMPANY_NAME),
      symbol = SYMBOL,
      technicalScore = round(TECHNICAL_SCORE, 1),
      tradingSignal = TRADING_SIGNAL,
      marketCap = MARKET_CAP_CATEGORY,
      currentPrice = round(CURRENT_PRICE, 2),
      rsi = round(RSI, 1),
      relativeStrength = round(RELATIVE_STRENGTH, 2),
      canSlim = CAN_SLIM_SCORE,
      minervini = MINERVINI_SCORE,
      fundamental = round(FUNDAMENTAL_SCORE, 1),
      trendSignal = TREND_SIGNAL,
      change1D = round(CHANGE_1D, 2),
      change1W = round(CHANGE_1W, 2),
      change1M = round(CHANGE_1M, 2)
    ) %>%
    select(companyName, symbol, technicalScore, tradingSignal, marketCap, 
           currentPrice, rsi, relativeStrength, canSlim, minervini, 
           fundamental, trendSignal, change1D, change1W, change1M)
  
  # Create JavaScript data
  js_data <- toJSON(stocks_data, pretty = TRUE)
  
  # Generate timestamp
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  # Create enhanced HTML content
  html_content <- sprintf('<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Market Analysis Dashboard - Enhanced</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-crosshair"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: "Roboto", "Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%%, #764ba2 100%%);
            min-height: 100vh;
            color: #212121;
            font-weight: 400;
            line-height: 1.6;
        }

        .container {
            max-width: 100%%;
            margin: 0 auto;
            padding: 20px;
            width: 100%%;
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

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 32px 24px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            text-align: center;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .stat-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 16px 48px rgba(0,0,0,0.2);
        }

        .stat-number {
            font-size: 3rem;
            font-weight: 300;
            color: #1976d2;
            margin-bottom: 12px;
            line-height: 1;
        }

        .stat-label {
            color: #616161;
            font-size: 0.875rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1.25px;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }

        .chart-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 24px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .chart-title {
            font-size: 1.25rem;
            font-weight: 500;
            color: #1976d2;
            margin-bottom: 20px;
            text-align: center;
        }

        .stocks-table-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 24px;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12);
            border: 1px solid rgba(255, 255, 255, 0.2);
            margin-bottom: 30px;
        }

        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .table-title {
            font-size: 1.5rem;
            font-weight: 500;
            color: #1976d2;
        }

        .filters {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 8px 16px;
            border: 2px solid #e0e0e0;
            background: white;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.3s ease;
            color: #666;
        }

        .filter-btn:hover {
            border-color: #1976d2;
            color: #1976d2;
        }

        .filter-btn.active {
            background: #1976d2;
            border-color: #1976d2;
            color: white;
        }

        .search-box {
            padding: 8px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 20px;
            font-size: 0.875rem;
            width: 200px;
            transition: border-color 0.3s ease;
        }

        .search-box:focus {
            outline: none;
            border-color: #1976d2;
        }

        .stocks-table {
            width: 100%%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }

        .stocks-table th {
            background: #f5f5f5;
            padding: 12px 8px;
            text-align: left;
            font-weight: 500;
            color: #666;
            border-bottom: 2px solid #e0e0e0;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .stocks-table td {
            padding: 12px 8px;
            border-bottom: 1px solid #f0f0f0;
            transition: background-color 0.2s ease;
        }

        .stocks-table tbody tr:hover {
            background-color: #f8f9fa;
        }

        .stocks-table tbody tr {
            cursor: pointer;
        }

        .signal-badge {
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
            text-align: center;
            min-width: 60px;
        }

        .signal-strong-buy { background: #4caf50; color: white; }
        .signal-buy { background: #8bc34a; color: white; }
        .signal-hold { background: #ff9800; color: white; }
        .signal-weak-hold { background: #ffc107; color: #333; }
        .signal-sell { background: #f44336; color: white; }

        .market-cap-badge {
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
            text-align: center;
            min-width: 70px;
        }

        .market-cap-large-cap { background: #2196f3; color: white; }
        .market-cap-mid-cap { background: #9c27b0; color: white; }
        .market-cap-small-cap { background: #ff5722; color: white; }
        .market-cap-micro-cap { background: #607d8b; color: white; }

        .trend-badge {
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
            text-align: center;
            min-width: 80px;
        }

        .trend-strong-bullish { background: #4caf50; color: white; }
        .trend-bullish { background: #8bc34a; color: white; }
        .trend-neutral { background: #ff9800; color: white; }
        .trend-bearish { background: #ff5722; color: white; }
        .trend-strong-bearish { background: #f44336; color: white; }

        .positive { color: #4caf50; font-weight: 500; }
        .negative { color: #f44336; font-weight: 500; }

        /* Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%%;
            height: 100%%;
            background-color: rgba(0,0,0,0.5);
            backdrop-filter: blur(5px);
        }

        .modal.active {
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-content {
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 95%%;
            max-height: 95%%;
            width: 1200px;
            overflow: hidden;
            animation: modalSlideIn 0.3s ease-out;
        }

        @keyframes modalSlideIn {
            from {
                opacity: 0;
                transform: scale(0.9) translateY(-20px);
            }
            to {
                opacity: 1;
                transform: scale(1) translateY(0);
            }
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 24px;
            border-bottom: 1px solid #e0e0e0;
            background: #f8f9fa;
        }

        .modal-title {
            font-size: 1.5rem;
            font-weight: 500;
            color: #1976d2;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 2rem;
            cursor: pointer;
            color: #666;
            padding: 0;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%%;
            transition: all 0.2s ease;
        }

        .modal-close:hover {
            background: #f0f0f0;
            color: #333;
        }

        .modal-body {
            padding: 24px;
            max-height: 80vh;
            overflow-y: auto;
        }

        .stock-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }

        .detail-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        .detail-item {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .detail-label {
            font-size: 0.875rem;
            color: #666;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .detail-value {
            font-size: 1.125rem;
            font-weight: 500;
            color: #333;
        }

        .signal-badge-modal, .market-cap-badge-modal, .trend-badge-modal {
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 0.875rem;
            font-weight: 500;
            text-align: center;
            display: inline-block;
        }

        /* Chart Container */
        .chart-section {
            margin-top: 30px;
        }

        .chart-wrapper {
            position: relative;
            height: 400px;
            margin-bottom: 20px;
        }

        .volume-chart-wrapper {
            position: relative;
            height: 150px;
        }

        .chart-controls {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }

        .chart-btn {
            padding: 6px 12px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.875rem;
            transition: all 0.2s ease;
        }

        .chart-btn:hover {
            background: #f0f0f0;
        }

        .chart-btn.active {
            background: #1976d2;
            color: white;
            border-color: #1976d2;
        }

        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 200px;
            color: #666;
            font-size: 1.125rem;
        }

        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #1976d2;
            border-radius: 50%%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }

        @keyframes spin {
            0%% { transform: rotate(0deg); }
            100%% { transform: rotate(360deg); }
        }

        @media (max-width: 768px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
            
            .stock-details {
                grid-template-columns: 1fr;
            }
            
            .detail-row {
                grid-template-columns: 1fr;
            }
            
            .modal-content {
                width: 95%%;
                margin: 20px;
            }
            
            .chart-wrapper {
                height: 300px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>NSE Market Analysis Dashboard</h1>
            <p>Enhanced with TradingView-like Charts - %s</p>
        </div>

        <div class="stats-grid" id="statsGrid">
            <!-- Stats will be populated by JavaScript -->
        </div>

        <div class="dashboard-grid">
            <div class="chart-container">
                <div class="chart-title">Trading Signals Distribution</div>
                <canvas id="signalsChart"></canvas>
            </div>
            <div class="chart-container">
                <div class="chart-title">Market Cap Performance</div>
                <canvas id="marketCapChart"></canvas>
            </div>
        </div>

        <div class="stocks-table-container">
            <div class="table-header">
                <div class="table-title">Stock Analysis Results</div>
                <div class="filters">
                    <input type="text" id="stockSearch" class="search-box" placeholder="Search stocks...">
                    <button class="filter-btn active" data-filter="all">All</button>
                    <button class="filter-btn" data-filter="STRONG_BUY">Strong Buy</button>
                    <button class="filter-btn" data-filter="BUY">Buy</button>
                    <button class="filter-btn" data-filter="HOLD">Hold</button>
                    <button class="filter-btn" data-filter="WEAK_HOLD">Weak Hold</button>
                    <button class="filter-btn" data-filter="SELL">Sell</button>
                </div>
            </div>
            <table class="stocks-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Symbol</th>
                        <th>Company</th>
                        <th>Price</th>
                        <th>1D</th>
                        <th>1W</th>
                        <th>1M</th>
                        <th>Score</th>
                        <th>Signal</th>
                        <th>Market Cap</th>
                        <th>RSI</th>
                        <th>RS</th>
                    </tr>
                </thead>
                <tbody id="stocksTableBody">
                    <!-- Table rows will be populated by JavaScript -->
                </tbody>
            </table>
        </div>
    </div>

    <!-- Enhanced Modal with Chart -->
    <div id="stockModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalStockSymbol"></div>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="stock-details" id="modalStockDetails">
                    <!-- Stock details will be populated here -->
                </div>
                
                <div class="chart-section">
                    <div class="chart-controls">
                        <button class="chart-btn active" data-period="1M">1M</button>
                        <button class="chart-btn" data-period="3M">3M</button>
                        <button class="chart-btn" data-period="6M">6M</button>
                        <button class="chart-btn" data-period="1Y">1Y</button>
                        <button class="chart-btn" data-period="ALL">ALL</button>
                    </div>
                    <div class="chart-wrapper">
                        <div class="loading" id="chartLoading">
                            <div class="spinner"></div>
                            Loading chart data...
                        </div>
                        <canvas id="stockChart" style="display: none;"></canvas>
                    </div>
                    <div class="volume-chart-wrapper">
                        <canvas id="volumeChart" style="display: none;"></canvas>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Stock data
        const stocksData = %s;
        
        // Chart instances
        let stockChart = null;
        let volumeChart = null;
        let currentStock = null;

        // Initialize the dashboard
        document.addEventListener("DOMContentLoaded", () => {
            initializeCharts();
            populateStocksTable(stocksData);
            updateStats();
            setupEventListeners();
        });

        function initializeCharts() {
            // Trading Signals Chart
            const signalsCtx = document.getElementById("signalsChart").getContext("2d");
            const signalsData = getSignalsDistribution();
            
            new Chart(signalsCtx, {
                type: "doughnut",
                data: {
                    labels: signalsData.labels,
                    datasets: [{
                        data: signalsData.data,
                        backgroundColor: [
                            "#4caf50", "#8bc34a", "#ff9800", "#ffc107", "#f44336"
                        ],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: "bottom",
                            labels: {
                                padding: 20,
                                usePointStyle: true
                            }
                        }
                    }
                }
            });

            // Market Cap Chart
            const marketCapCtx = document.getElementById("marketCapChart").getContext("2d");
            const marketCapData = getMarketCapDistribution();
            
            new Chart(marketCapCtx, {
                type: "bar",
                data: {
                    labels: marketCapData.labels,
                    datasets: [{
                        label: "Average Score",
                        data: marketCapData.scores,
                        backgroundColor: "#1976d2",
                        borderRadius: 8,
                        borderSkipped: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100
                        }
                    }
                }
            });
        }

        function getSignalsDistribution() {
            const signals = {};
            stocksData.forEach(stock => {
                signals[stock.tradingSignal] = (signals[stock.tradingSignal] || 0) + 1;
            });
            
            return {
                labels: Object.keys(signals),
                data: Object.values(signals)
            };
        }

        function getMarketCapDistribution() {
            const marketCaps = {};
            stocksData.forEach(stock => {
                if (!marketCaps[stock.marketCap]) {
                    marketCaps[stock.marketCap] = { count: 0, totalScore: 0 };
                }
                marketCaps[stock.marketCap].count++;
                marketCaps[stock.marketCap].totalScore += stock.technicalScore;
            });
            
            const labels = Object.keys(marketCaps);
            const scores = labels.map(cap => 
                (marketCaps[cap].totalScore / marketCaps[cap].count).toFixed(1)
            );
            
            return { labels, scores };
        }

        function updateStats() {
            const statsGrid = document.getElementById("statsGrid");
            const totalStocks = stocksData.length;
            const strongBuys = stocksData.filter(s => s.tradingSignal === "STRONG_BUY").length;
            const buys = stocksData.filter(s => s.tradingSignal === "BUY").length;
            const avgScore = (stocksData.reduce((sum, s) => sum + s.technicalScore, 0) / totalStocks).toFixed(1);
            
            statsGrid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-number">${totalStocks}</div>
                    <div class="stat-label">Total Stocks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${strongBuys + buys}</div>
                    <div class="stat-label">Buy Signals</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${avgScore}</div>
                    <div class="stat-label">Avg Score</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${strongBuys}</div>
                    <div class="stat-label">Strong Buys</div>
                </div>
            `;
        }

        function populateStocksTable(stocks) {
            const tbody = document.getElementById("stocksTableBody");
            tbody.innerHTML = "";
            
            stocks.forEach((stock, index) => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td>${index + 1}</td>
                    <td><strong>${stock.symbol}</strong></td>
                    <td>${stock.companyName}</td>
                    <td>₹${stock.currentPrice.toLocaleString()}</td>
                    <td class="${stock.change1D >= 0 ? "positive" : "negative"}">${stock.change1D >= 0 ? "+" : ""}${stock.change1D.toFixed(2)}%%</td>
                    <td class="${stock.change1W >= 0 ? "positive" : "negative"}">${stock.change1W >= 0 ? "+" : ""}${stock.change1W.toFixed(2)}%%</td>
                    <td class="${stock.change1M >= 0 ? "positive" : "negative"}">${stock.change1M >= 0 ? "+" : ""}${stock.change1M.toFixed(2)}%%</td>
                    <td><strong>${stock.technicalScore}</strong></td>
                    <td><span class="signal-badge signal-${stock.tradingSignal.toLowerCase().replace("_", "-")}">${stock.tradingSignal.replace("_", " ")}</span></td>
                    <td><span class="market-cap-badge market-cap-${stock.marketCap.toLowerCase().replace("_", "-")}">${stock.marketCap.replace("_", " ")}</span></td>
                    <td>${stock.rsi}</td>
                    <td class="${stock.relativeStrength >= 0 ? "positive" : "negative"}">${stock.relativeStrength >= 0 ? "+" : ""}${stock.relativeStrength.toFixed(2)}%%</td>
                `;
                
                row.style.cursor = "pointer";
                row.addEventListener("click", () => showStockDetails(stock));
                tbody.appendChild(row);
            });
        }

        function showStockDetails(stock) {
            currentStock = stock;
            const modal = document.getElementById("stockModal");
            const modalSymbol = document.getElementById("modalStockSymbol");
            const modalDetails = document.getElementById("modalStockDetails");
            
            // Update modal title
            modalSymbol.textContent = `${stock.companyName} (${stock.symbol})`;
            
            // Create detailed content
            const detailsHTML = `
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Company Name</div>
                        <div class="detail-value">${stock.companyName}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Stock Symbol</div>
                        <div class="detail-value">${stock.symbol}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Technical Score</div>
                        <div class="detail-value">${stock.technicalScore}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Trading Signal</div>
                        <div class="signal-badge-modal signal-${stock.tradingSignal.toLowerCase().replace("_", "-")}-modal">${stock.tradingSignal.replace("_", " ")}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Market Cap</div>
                        <div class="market-cap-badge-modal market-cap-${stock.marketCap.toLowerCase().replace("_", "-")}-modal">${stock.marketCap.replace("_", " ")}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Current Price</div>
                        <div class="detail-value">₹${stock.currentPrice.toLocaleString()}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">RSI</div>
                        <div class="detail-value">${stock.rsi}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Relative Strength</div>
                        <div class="detail-value ${stock.relativeStrength >= 0 ? "positive" : "negative"}">${stock.relativeStrength >= 0 ? "+" : ""}${stock.relativeStrength.toFixed(2)}%%</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">CAN SLIM Score</div>
                        <div class="detail-value">${stock.canSlim}/25</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Minervini Score</div>
                        <div class="detail-value">${stock.minervini}/20</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">Fundamental Score</div>
                        <div class="detail-value">${stock.fundamental.toFixed(1)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Trend Signal</div>
                        <div class="trend-badge-modal trend-${stock.trendSignal.toLowerCase().replace("_", "-")}-modal">${stock.trendSignal.replace("_", " ")}</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">1 Day Change</div>
                        <div class="detail-value ${stock.change1D >= 0 ? "positive" : "negative"}">${stock.change1D >= 0 ? "+" : ""}${stock.change1D.toFixed(2)}%%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">1 Week Change</div>
                        <div class="detail-value ${stock.change1W >= 0 ? "positive" : "negative"}">${stock.change1W >= 0 ? "+" : ""}${stock.change1W.toFixed(2)}%%</div>
                    </div>
                </div>
                
                <div class="detail-row">
                    <div class="detail-item">
                        <div class="detail-label">1 Month Change</div>
                        <div class="detail-value ${stock.change1M >= 0 ? "positive" : "negative"}">${stock.change1M >= 0 ? "+" : ""}${stock.change1M.toFixed(2)}%%</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Analysis Date</div>
                        <div class="detail-value">2025-09-22</div>
                    </div>
                </div>
            `;
            
            modalDetails.innerHTML = detailsHTML;
            
            // Show modal
            modal.classList.add("active");
            
            // Load chart data
            loadStockChart(stock.symbol);
            
            // Setup chart period controls
            setupChartControls();
        }

        function loadStockChart(symbol) {
            const chartLoading = document.getElementById("chartLoading");
            const stockChartCanvas = document.getElementById("stockChart");
            const volumeChartCanvas = document.getElementById("volumeChart");
            
            // Show loading
            chartLoading.style.display = "flex";
            stockChartCanvas.style.display = "none";
            volumeChartCanvas.style.display = "none";
            
            // Simulate loading chart data (in real implementation, this would fetch from server)
            setTimeout(() => {
                // Generate sample candlestick data
                const chartData = generateSampleChartData(symbol);
                
                // Create candlestick chart
                createCandlestickChart(chartData);
                
                // Create volume chart
                createVolumeChart(chartData);
                
                // Hide loading, show charts
                chartLoading.style.display = "none";
                stockChartCanvas.style.display = "block";
                volumeChartCanvas.style.display = "block";
            }, 1000);
        }

        function generateSampleChartData(symbol) {
            // Generate sample OHLCV data for demonstration
            const data = [];
            const basePrice = stocksData.find(s => s.symbol === symbol)?.currentPrice || 100;
            let currentPrice = basePrice;
            const startDate = new Date();
            startDate.setDate(startDate.getDate() - 200); // 200 days ago
            
            for (let i = 0; i < 200; i++) {
                const date = new Date(startDate);
                date.setDate(date.getDate() + i);
                
                // Generate realistic price movement
                const change = (Math.random() - 0.5) * 0.05; // ±2.5%% daily change
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
        }

        function createCandlestickChart(data) {
            const ctx = document.getElementById("stockChart").getContext("2d");
            
            // Destroy existing chart
            if (stockChart) {
                stockChart.destroy();
            }
            
            stockChart = new Chart(ctx, {
                type: "candlestick",
                data: {
                    datasets: [{
                        label: `${currentStock.symbol} Price`,
                        data: data,
                        color: {
                            up: "#4caf50",
                            down: "#f44336",
                            unchanged: "#666"
                        },
                        borderColor: {
                            up: "#4caf50",
                            down: "#f44336",
                            unchanged: "#666"
                        }
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        zoom: {
                            pan: {
                                enabled: true,
                                mode: "x"
                            },
                            zoom: {
                                wheel: {
                                    enabled: true
                                },
                                pinch: {
                                    enabled: true
                                },
                                mode: "x"
                            }
                        }
                    },
                    scales: {
                        x: {
                            type: "time",
                            time: {
                                unit: "day"
                            }
                        },
                        y: {
                            position: "right"
                        }
                    }
                }
            });
        }

        function createVolumeChart(data) {
            const ctx = document.getElementById("volumeChart").getContext("2d");
            
            // Destroy existing chart
            if (volumeChart) {
                volumeChart.destroy();
            }
            
            const volumeData = data.map(d => ({
                x: d.x,
                y: d.v
            }));
            
            volumeChart = new Chart(ctx, {
                type: "bar",
                data: {
                    datasets: [{
                        label: "Volume",
                        data: volumeData,
                        backgroundColor: "#1976d2",
                        borderColor: "#1976d2",
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        x: {
                            type: "time",
                            time: {
                                unit: "day"
                            },
                            display: false
                        },
                        y: {
                            position: "right",
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        function setupChartControls() {
            const chartBtns = document.querySelectorAll(".chart-btn");
            chartBtns.forEach(btn => {
                btn.addEventListener("click", () => {
                    chartBtns.forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    
                    const period = btn.dataset.period;
                    // In real implementation, this would reload chart data for the selected period
                    console.log(`Loading chart data for period: ${period}`);
                });
            });
        }

        function setupEventListeners() {
            const modal = document.getElementById("stockModal");
            const filterBtns = document.querySelectorAll(".filter-btn");
            const searchBox = document.getElementById("stockSearch");

            filterBtns.forEach(btn => {
                btn.addEventListener("click", () => {
                    filterBtns.forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    applyFilters();
                });
            });

            searchBox.addEventListener("input", applyFilters);
            
            // Close modal when clicking outside
            modal.addEventListener("click", function(e) {
                if (e.target === modal) {
                    closeModal();
                }
            });
            
            // Close modal with Escape key
            document.addEventListener("keydown", function(e) {
                if (e.key === "Escape" && modal.classList.contains("active")) {
                    closeModal();
                }
            });
        }

        function applyFilters() {
            const searchTerm = document.getElementById("stockSearch").value.toLowerCase();
            const activeFilter = document.querySelector(".filter-btn.active").dataset.filter;
            
            let filteredStocks = stocksData;
            
            if (activeFilter !== "all") {
                filteredStocks = filteredStocks.filter(stock => stock.tradingSignal === activeFilter);
            }
            
            if (searchTerm) {
                filteredStocks = filteredStocks.filter(stock => 
                    stock.symbol.toLowerCase().includes(searchTerm) ||
                    stock.companyName.toLowerCase().includes(searchTerm)
                );
            }
            
            populateStocksTable(filteredStocks);
        }

        function closeModal() {
            const modal = document.getElementById("stockModal");
            modal.classList.remove("active");
            
            // Destroy charts to free memory
            if (stockChart) {
                stockChart.destroy();
                stockChart = null;
            }
            if (volumeChart) {
                volumeChart.destroy();
                volumeChart = null;
            }
        }
    </script>
</body>
</html>', 
    format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
    js_data
  )
  
  # Save the enhanced dashboard
  output_file <- sprintf("reports/NSE_Enhanced_Dashboard_%s.html", timestamp)
  writeLines(html_content, output_file)
  
  cat(sprintf("Enhanced dashboard saved to: %s\n", output_file))
  return(output_file)
}

# Main execution
if (!interactive()) {
  enhanced_dashboard_file <- generate_enhanced_dashboard()
  cat("Enhanced dashboard generation completed successfully!\n")
}
