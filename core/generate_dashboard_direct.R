# Simple script to generate dashboard directly from CSV
suppressMessages({
  library(dplyr)
})

# Read CSV data
csv_data <- read.csv('Nifty50_Intraday_Analysis_20250812.csv', stringsAsFactors = FALSE)
cat('📊 Loaded', nrow(csv_data), 'symbols from CSV\n')

# Create date-only string for filename
today_date <- format(Sys.Date(), "%Y%m%d")
dashboard_file <- paste0("Nifty50_Intraday_Dashboard_", today_date, ".html")

# Get current timestamp
current_time <- format(Sys.time(), "%B %d, %Y at %H:%M")

# Start HTML content  
html_content <- paste0('<!DOCTYPE html>
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
        
        .view-controls {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            border-bottom: 1px solid #dee2e6;
        }
        
        .view-toggle {
            background: linear-gradient(135deg, #6f42c1, #6610f2);
            color: white;
            border: none;
            padding: 12px 24px;
            margin: 0 10px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .view-toggle.active {
            background: linear-gradient(135deg, #28a745, #20c997);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3);
        }
        
        /* Table View */
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
            cursor: pointer;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .stocks-table td {
            padding: 12px 10px;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: middle;
        }
        
        .stocks-table tbody tr:hover {
            background-color: #f8f9fa;
        }
        
        .sentiment-bullish { color: #28a745; font-weight: bold; }
        .sentiment-bearish { color: #dc3545; font-weight: bold; }
        .sentiment-neutral { color: #6c757d; font-weight: bold; }
        
        .score-high { background: #d4edda; }
        .score-medium { background: #fff3cd; }
        .score-low { background: #f8d7da; }
        
        /* Card View */
        .card-container {
            display: none;
            padding: 20px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .stock-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .stock-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }
        
        .stock-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .stock-symbol {
            font-size: 1.4em;
            font-weight: bold;
            color: #2c3e50;
        }
        
        .score-badge {
            padding: 6px 12px;
            border-radius: 20px;
            color: white;
            font-weight: bold;
            font-size: 0.9em;
        }
        
        .score-high { background: linear-gradient(135deg, #28a745, #20c997); }
        .score-medium { background: linear-gradient(135deg, #ffc107, #fd7e14); }
        .score-low { background: linear-gradient(135deg, #dc3545, #e83e8c); }
        
        .stock-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 15px;
        }
        
        .detail-item {
            text-align: center;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 6px;
        }
        
        .detail-label {
            font-size: 0.85em;
            color: #6c757d;
            margin-bottom: 2px;
        }
        
        .detail-value {
            font-weight: bold;
            color: #2c3e50;
        }
        
        .summary-stats {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            border-bottom: 1px solid #dee2e6;
        }
        
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }
        
        .stat-item {
            background: white;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #2c3e50;
        }
        
        .stat-label {
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Nifty50 Intraday Technical Analysis</h1>
            <p>Real-time technical analysis and signals for Nifty50 stocks</p>
            <p>Generated on: ', current_time, '</p>
        </div>
        
        <div class="summary-stats">
            <h3>Portfolio Overview</h3>
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-value" id="totalStocks">', nrow(csv_data), '</div>
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
        </div>
        
        <div class="view-controls">
            <button class="view-toggle active" onclick="showTableView()">📊 Table View</button>
            <button class="view-toggle" onclick="showCardView()">🃏 Card View</button>
        </div>
        
        <div id="tableView" class="table-container">
            <table class="stocks-table">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Symbol ↕</th>
                        <th onclick="sortTable(1)">Score ↕</th>
                        <th onclick="sortTable(2)">Sentiment ↕</th>
                        <th onclick="sortTable(3)">Price ↕</th>
                        <th onclick="sortTable(4)">Change ↕</th>
                        <th onclick="sortTable(5)">Change % ↕</th>
                        <th onclick="sortTable(6)">Data Points ↕</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                </tbody>
            </table>
        </div>
        
        <div id="cardView" class="card-container">
        </div>
    </div>
    
    <script>
        const stockData = [')

# Convert CSV data to JavaScript
js_data_lines <- c()
for(i in 1:nrow(csv_data)) {
  row <- csv_data[i,]
  
  # Clean symbol name
  symbol <- gsub('"', '', row$Symbol)
  
  # Get numeric values safely
  score <- as.numeric(row$Technical_Score)
  if(is.na(score)) score <- 50
  
  price <- row$Current_Price
  if(price == "Index") price <- "Index"
  else {
    price <- as.numeric(price)
    if(is.na(price)) price <- 0
  }
  
  change <- row$Price_Change
  if(change == "N/A") change <- 0
  else {
    change <- as.numeric(change)
    if(is.na(change)) change <- 0
  }
  
  change_pct <- row$Price_Change_Pct
  if(change_pct == "N/A") change_pct <- 0
  else {
    change_pct <- as.numeric(change_pct)
    if(is.na(change_pct)) change_pct <- 0
  }
  
  data_points <- as.numeric(row$Data_Points)
  if(is.na(data_points)) data_points <- 0
  
  # Determine sentiment
  sentiment <- if(score >= 60) "bullish" else if(score <= 40) "bearish" else "neutral"
  
  # Create JavaScript object
  js_line <- paste0('
            {
                symbol: "', symbol, '",
                score: ', score, ',
                sentiment: "', sentiment, '",
                price: ', if(price == "Index") '"Index"' else price, ',
                change: ', change, ',
                changePct: ', change_pct, ',
                dataPoints: ', data_points, '
            }')
  
  js_data_lines <- c(js_data_lines, js_line)
}

# Join all JavaScript data
js_data <- paste(js_data_lines, collapse = ',')

# Continue HTML with JavaScript
html_content <- paste0(html_content, js_data, '
        ];
        
        function updateSummaryStats() {
            const totalStocks = stockData.length;
            const bullishCount = stockData.filter(s => s.sentiment === "bullish").length;
            const bearishCount = stockData.filter(s => s.sentiment === "bearish").length;
            const neutralCount = stockData.filter(s => s.sentiment === "neutral").length;
            const avgScore = totalStocks > 0 ? Math.round(stockData.reduce((sum, s) => sum + s.score, 0) / totalStocks) : 0;
            
            document.getElementById("totalStocks").textContent = totalStocks;
            document.getElementById("bullishCount").textContent = bullishCount;
            document.getElementById("bearishCount").textContent = bearishCount;
            document.getElementById("neutralCount").textContent = neutralCount;
            document.getElementById("avgScore").textContent = avgScore;
        }
        
        function populateTable() {
            const tableBody = document.getElementById("tableBody");
            tableBody.innerHTML = "";
            
            stockData.forEach(stock => {
                const row = document.createElement("tr");
                
                const scoreClass = stock.score >= 60 ? "score-high" : stock.score <= 40 ? "score-low" : "score-medium";
                const sentimentClass = `sentiment-${stock.sentiment}`;
                
                row.innerHTML = `
                    <td><strong>${stock.symbol}</strong></td>
                    <td class="${scoreClass}">${stock.score}</td>
                    <td class="${sentimentClass}">${stock.sentiment.toUpperCase()}</td>
                    <td>${stock.price === "Index" ? "Index" : stock.price.toFixed(2)}</td>
                    <td class="${stock.change >= 0 ? "sentiment-bullish" : "sentiment-bearish"}">${stock.change >= 0 ? "+" : ""}${stock.change.toFixed(2)}</td>
                    <td class="${stock.changePct >= 0 ? "sentiment-bullish" : "sentiment-bearish"}">${stock.changePct >= 0 ? "+" : ""}${stock.changePct.toFixed(2)}%</td>
                    <td>${stock.dataPoints}</td>
                `;
                
                tableBody.appendChild(row);
            });
        }
        
        function populateCards() {
            const cardContainer = document.getElementById("cardView");
            cardContainer.innerHTML = "";
            
            stockData.forEach(stock => {
                const scoreClass = stock.score >= 60 ? "score-high" : stock.score <= 40 ? "score-low" : "score-medium";
                const sentimentClass = `sentiment-${stock.sentiment}`;
                
                const card = document.createElement("div");
                card.className = "stock-card";
                card.innerHTML = `
                    <div class="stock-header">
                        <div class="stock-symbol">${stock.symbol}</div>
                        <div class="score-badge ${scoreClass}">${stock.score}</div>
                    </div>
                    <div class="stock-details">
                        <div class="detail-item">
                            <div class="detail-label">Sentiment</div>
                            <div class="detail-value ${sentimentClass}">${stock.sentiment.toUpperCase()}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Price</div>
                            <div class="detail-value">${stock.price === "Index" ? "Index" : stock.price.toFixed(2)}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Change</div>
                            <div class="detail-value ${stock.change >= 0 ? "sentiment-bullish" : "sentiment-bearish"}">${stock.change >= 0 ? "+" : ""}${stock.change.toFixed(2)}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Change %</div>
                            <div class="detail-value ${stock.changePct >= 0 ? "sentiment-bullish" : "sentiment-bearish"}">${stock.changePct >= 0 ? "+" : ""}${stock.changePct.toFixed(2)}%</div>
                        </div>
                    </div>
                `;
                
                cardContainer.appendChild(card);
            });
        }
        
        function showTableView() {
            document.getElementById("tableView").style.display = "block";
            document.getElementById("cardView").style.display = "none";
            document.querySelectorAll(".view-toggle").forEach(btn => btn.classList.remove("active"));
            event.target.classList.add("active");
        }
        
        function showCardView() {
            document.getElementById("tableView").style.display = "none";
            document.getElementById("cardView").style.display = "grid";
            document.querySelectorAll(".view-toggle").forEach(btn => btn.classList.remove("active"));
            event.target.classList.add("active");
        }
        
        function sortTable(columnIndex) {
            const table = document.querySelector(".stocks-table");
            const tbody = table.querySelector("tbody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            
            rows.sort((a, b) => {
                const aValue = a.cells[columnIndex].textContent.trim();
                const bValue = b.cells[columnIndex].textContent.trim();
                
                if (!isNaN(aValue) && !isNaN(bValue)) {
                    return parseFloat(bValue) - parseFloat(aValue);
                }
                return aValue.localeCompare(bValue);
            });
            
            rows.forEach(row => tbody.appendChild(row));
        }
        
        // Initialize the dashboard
        document.addEventListener("DOMContentLoaded", function() {
            updateSummaryStats();
            populateTable();
            populateCards();
        });
    </script>
</body>
</html>')

# Write the HTML file
writeLines(html_content, dashboard_file)

cat('✅ Dashboard generated successfully!\n')
cat('📂 File:', dashboard_file, '\n')
cat('📊 Contains', nrow(csv_data), 'stocks\n')

# Print summary
bullish_count <- sum(csv_data$Technical_Score >= 60, na.rm = TRUE)
bearish_count <- sum(csv_data$Technical_Score <= 40, na.rm = TRUE)
neutral_count <- nrow(csv_data) - bullish_count - bearish_count
avg_score <- round(mean(csv_data$Technical_Score, na.rm = TRUE), 1)

cat('\n📈 Summary:\n')
cat('   • Total Stocks:', nrow(csv_data), '\n')
cat('   • Bullish (≥60):', bullish_count, '\n')
cat('   • Bearish (≤40):', bearish_count, '\n')
cat('   • Neutral:', neutral_count, '\n')
cat('   • Average Score:', avg_score, '\n')
