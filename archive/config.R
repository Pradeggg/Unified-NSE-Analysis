# ================================================================================
# UNIFIED NSE ANALYSIS - CONFIGURATION FILE
# ================================================================================
# Version: 1.0
# Created: August 2025
# Purpose: Central configuration for unified NSE stock and index analysis
# ================================================================================

# Project paths
PROJECT_ROOT <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis"
LEGACY_DATA_PATH <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index"

# Directory structure
DIRS <- list(
  core = file.path(PROJECT_ROOT, "core"),
  optimization = file.path(PROJECT_ROOT, "optimization"), 
  legacy = file.path(PROJECT_ROOT, "legacy"),
  helpers = file.path(PROJECT_ROOT, "helpers"),
  data = file.path(PROJECT_ROOT, "data"),
  output = file.path(PROJECT_ROOT, "output"),
  logs = file.path(PROJECT_ROOT, "logs")
)

# Data file configurations
DATA_FILES <- list(
  # Index data
  index_data = file.path(LEGACY_DATA_PATH, "nse_index_data.csv"),
  
  # Stock data  
  stock_data = file.path(LEGACY_DATA_PATH, "nse_sec_full_data.csv"),
  mto_data = file.path(LEGACY_DATA_PATH, "nse_mto_data.csv"),
  circuit_breakers = file.path(LEGACY_DATA_PATH, "nse_circuit_breakers_data.csv"),
  
  # Helper files
  helpers = file.path(LEGACY_DATA_PATH, "helpers.R"),
  data_loader = file.path(LEGACY_DATA_PATH, "getdataNSE.R")
)

# Analysis configurations
ANALYSIS_CONFIG <- list(
  # Technical analysis parameters
  ema_periods = c(20, 30, 40, 50, 100, 150, 200),
  vema_periods = c(20, 30, 50, 100, 150, 200),
  rsi_period = 14,
  macd_params = list(nFast = 12, nSlow = 26, nSig = 9),
  aroon_period = 14,
  bollinger_params = list(sd = 2.0, n = 20),
  
  # Return calculation periods
  gain_periods = c(5, 10, 20, 30, 50, 100),
  logret_periods = c(5, 10, 15, 30, 50, 100, 150, 365),
  
  # Data filtering
  min_historical_days = 200,
  historical_years = 7,
  
  # Performance optimization
  parallel_processing = TRUE,
  chunk_size = 500,
  max_cores = parallel::detectCores() - 1
)

# Output configurations
OUTPUT_CONFIG <- list(
  # File naming patterns
  index_analysis_pattern = "index_analysis_%s.csv",
  stock_analysis_pattern = "stock_analysis_%s.csv",
  consolidated_pattern = "consolidated_analysis_%s.csv",
  
  # Output directories
  daily_outputs = file.path(DIRS$output, "daily"),
  historical_outputs = file.path(DIRS$output, "historical"),
  reports = file.path(DIRS$output, "reports"),
  
  # Log configurations
  log_level = "INFO", # DEBUG, INFO, WARN, ERROR
  log_file_pattern = "analysis_%s.log"
)

# Ensure output directories exist
for(dir_path in c(OUTPUT_CONFIG$daily_outputs, OUTPUT_CONFIG$historical_outputs, OUTPUT_CONFIG$reports)) {
  if(!dir.exists(dir_path)) {
    dir.create(dir_path, recursive = TRUE)
  }
}

# Logging configuration
LOG_CONFIG <- list(
  enabled = TRUE,
  file = file.path(DIRS$logs, sprintf(OUTPUT_CONFIG$log_file_pattern, format(Sys.Date(), "%Y%m%d"))),
  console = TRUE,
  timestamp_format = "%Y-%m-%d %H:%M:%S"
)

# Stock configuration
STOCK_CONFIG <- list(
  watchlist_stocks = c("RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK"),
  benchmark_index = "NIFTY",
  analysis_period = 252, # trading days in a year
  min_volume_filter = 100000
)

# Create consolidated configuration object
PROJECT_CONFIG <- list(
  paths = list(
    project_root = PROJECT_ROOT,
    legacy_data = LEGACY_DATA_PATH,
    dirs = DIRS
  ),
  data_files = DATA_FILES,
  analysis = ANALYSIS_CONFIG,
  logging = LOG_CONFIG,
  stocks = STOCK_CONFIG
)

# Print configuration summary
cat("=== UNIFIED NSE ANALYSIS CONFIGURATION ===\n")
cat("Project Root:", PROJECT_ROOT, "\n")
cat("Legacy Data Path:", LEGACY_DATA_PATH, "\n")
cat("Log File:", LOG_CONFIG$file, "\n")
cat("Parallel Processing:", ANALYSIS_CONFIG$parallel_processing, "\n")
cat("Max Cores:", ANALYSIS_CONFIG$max_cores, "\n")
cat("==========================================\n")
