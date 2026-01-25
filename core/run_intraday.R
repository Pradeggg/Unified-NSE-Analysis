#!/usr/bin/env Rscript

# Load required libraries
cat("Loading libraries...\n")
library(quantmod)
library(dplyr)
library(lubridate)

# Source the main analysis file
cat("Loading intraday analysis functions...\n")
source("intraday_yahoo.R")

# Run the analysis
cat("🚀 Starting Complete Intraday Analysis...\n")
cat("📊 Analyzing all Nifty50 stocks + major indices\n")

# Get start time
start_time <- Sys.time()

# Run the complete analysis
results <- analyze_nifty50_intraday("1h")

# Calculate elapsed time
end_time <- Sys.time()
elapsed <- as.numeric(difftime(end_time, start_time, units = "mins"))

cat("✅ Analysis completed in", round(elapsed, 2), "minutes\n")
cat("📂 Files generated:\n")

# List generated files
files <- list.files(pattern = "Nifty50.*\\.csv|Nifty50.*\\.html", full.names = FALSE)
for(file in files) {
  info <- file.info(file)
  cat("   •", file, "(", round(info$size/1024, 1), "KB )\n")
}

cat("🎯 Ready for trading analysis!\n")
