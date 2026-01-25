# =============================================================================
# ENHANCED NSE ANALYSIS SYSTEM DEMONSTRATION
# This script demonstrates the enhanced system with SQLite database integration
# and trend analysis capabilities
# =============================================================================

cat("🚀 ENHANCED NSE ANALYSIS SYSTEM DEMONSTRATION\n")
cat("=============================================\n\n")

# Set working directory
setwd('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts')

# Database path
db_path <- '/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/data/nse_analysis.db'

# =============================================================================
# STEP 1: Run the Enhanced Analysis (with Database Storage)
# =============================================================================

cat("📊 STEP 1: Running Enhanced NSE Analysis with Database Storage\n")
cat("==============================================================\n")

# Source the enhanced analysis script
source('fixed_nse_universe_analysis.R')

cat("\n✅ Enhanced analysis completed and results saved to database!\n\n")

# =============================================================================
# STEP 2: Run Trend Analysis
# =============================================================================

cat("📈 STEP 2: Running Trend Analysis Module\n")
cat("========================================\n")

# Source the trend analysis module
source('./trend_analysis_module.R')

# Run trend analysis for the last 15 days
cat("Running trend analysis for the last 15 days...\n")
trend_results <- run_trend_analysis(db_path, days_back = 15, save_to_db = TRUE)

cat("\n✅ Trend analysis completed!\n\n")

# =============================================================================
# STEP 3: Database Query Examples
# =============================================================================

cat("🗄️ STEP 3: Database Query Examples\n")
cat("===================================\n")

# Load required libraries
suppressMessages({
  library(RSQLite)
  library(DBI)
  library(dplyr)
})

# Connect to database
conn <- dbConnect(RSQLite::SQLite(), db_path)

# Example 1: Get latest market breadth data
cat("📊 Latest Market Breadth Data:\n")
breadth_query <- "
  SELECT * FROM market_breadth 
  ORDER BY analysis_date DESC 
  LIMIT 5
"
breadth_data <- dbGetQuery(conn, breadth_query)
print(breadth_data)

cat("\n")

# Example 2: Get top performing stocks from latest analysis
cat("🏆 Top 10 Stocks from Latest Analysis:\n")
stocks_query <- "
  SELECT symbol, company_name, technical_score, trading_signal, trend_signal
  FROM stocks_analysis 
  WHERE analysis_date = (SELECT MAX(analysis_date) FROM stocks_analysis)
  ORDER BY technical_score DESC 
  LIMIT 10
"
top_stocks <- dbGetQuery(conn, stocks_query)
print(top_stocks)

cat("\n")

# Example 3: Get index performance trends
cat("🏛️ Latest Index Performance:\n")
index_query <- "
  SELECT index_name, technical_score, trading_signal, trend_signal
  FROM index_analysis 
  WHERE analysis_date = (SELECT MAX(analysis_date) FROM index_analysis)
  ORDER BY technical_score DESC
"
index_performance <- dbGetQuery(conn, index_query)
print(index_performance)

cat("\n")

# Example 4: Get trend analysis data
cat("📈 Recent Trend Analysis Data:\n")
trend_query <- "
  SELECT analysis_date, analysis_type, metric_name, latest_value, change_percentage, trend_direction
  FROM trend_analysis 
  WHERE analysis_date >= date('now', '-7 days')
  ORDER BY analysis_date DESC, analysis_type, metric_name
  LIMIT 20
"
trend_data <- dbGetQuery(conn, trend_query)
print(trend_data)

# Close database connection
dbDisconnect(conn)

cat("\n✅ Database queries completed!\n\n")

# =============================================================================
# STEP 4: System Summary
# =============================================================================

cat("📋 SYSTEM ENHANCEMENT SUMMARY\n")
cat("=============================\n")
cat("✅ SQLite Database Integration:\n")
cat("   - stocks_analysis table: Stores daily stock analysis results\n")
cat("   - index_analysis table: Stores daily index analysis results\n")
cat("   - market_breadth table: Stores daily market breadth metrics\n")
cat("   - trend_analysis table: Stores trend analysis results\n\n")

cat("✅ Enhanced Features:\n")
cat("   - Automatic database initialization and table creation\n")
cat("   - Daily analysis results automatically saved to database\n")
cat("   - Historical data storage for trend analysis\n")
cat("   - Comprehensive 15-day trend analysis module\n")
cat("   - Market breadth trend tracking\n")
cat("   - Index performance trend analysis\n")
cat("   - Top performers trend analysis\n\n")

cat("✅ Database Location:\n")
cat("   ", db_path, "\n\n")

cat("✅ Available Functions:\n")
cat("   - initialize_database(): Initialize database and create tables\n")
cat("   - save_stocks_to_database(): Save stock analysis results\n")
cat("   - save_indices_to_database(): Save index analysis results\n")
cat("   - save_market_breadth_to_database(): Save market breadth data\n")
cat("   - run_trend_analysis(): Run comprehensive trend analysis\n")
cat("   - get_historical_data(): Retrieve historical data from database\n\n")

cat("🎯 NEXT STEPS:\n")
cat("1. Run the enhanced analysis daily to build historical database\n")
cat("2. Use trend analysis module to identify market trends\n")
cat("3. Query database for custom analysis and reporting\n")
cat("4. Build dashboards using historical data\n\n")

cat("🚀 Enhanced NSE Analysis System is ready for production use!\n")
