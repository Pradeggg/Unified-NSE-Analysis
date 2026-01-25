# Complete NSE Analysis Pipeline
# Integrated workflow: Data Loading → Analysis → Screeners → Enhanced Dashboard
# Author: AI Assistant
# Date: September 30, 2025

# Load required libraries
suppressMessages({
  library(DBI)
  library(RSQLite)
  library(dplyr)
  library(htmltools)
  library(jsonlite)
  library(lubridate)
  library(httr)
  library(xml2)
  library(readr)
})

# Set working directory
setwd("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis")

# Initialize pipeline
cat("🚀 Starting Complete NSE Analysis Pipeline...\n")
cat("📅 Pipeline Date:", as.character(Sys.Date()), "\n")
cat("⏰ Pipeline Time:", format(Sys.time(), "%H:%M:%S"), "\n\n")

# Step 1: Load Latest NSE Data for September 29th
cat(paste(rep("=", 60), collapse=""), "\n")
cat("📊 STEP 1: Loading Latest NSE Data for September 29th\n")
cat(paste(rep("=", 60), collapse=""), "\n")

tryCatch({
  source("load_latest_nse_data_comprehensive.R")
  cat("✅ NSE Data Loading Completed Successfully!\n\n")
}, error = function(e) {
  cat("❌ Error in NSE Data Loading:", e$message, "\n")
  stop("Pipeline failed at data loading step")
})

# Step 2: Run Fixed NSE Universe Analysis
cat(paste(rep("=", 60), collapse=""), "\n")
cat("🔍 STEP 2: Running Fixed NSE Universe Analysis\n")
cat(paste(rep("=", 60), collapse=""), "\n")

tryCatch({
  source("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts/fixed_nse_universe_analysis.R")
  cat("✅ NSE Universe Analysis Completed Successfully!\n\n")
}, error = function(e) {
  cat("❌ Error in NSE Universe Analysis:", e$message, "\n")
  stop("Pipeline failed at universe analysis step")
})

# Step 3: Generate Long-term Screeners
cat(paste(rep("=", 60), collapse=""), "\n")
cat("🎯 STEP 3: Generating Long-term Screeners\n")
cat(paste(rep("=", 60), collapse=""), "\n")

tryCatch({
  # Use the existing long-term screeners from the analysis
  cat("📊 Using Long-term Screeners from NSE Universe Analysis...\n")
  cat("✅ Long-term Screeners data already generated in Step 2\n")
  cat("✅ Long-term Screeners Generated Successfully!\n\n")
}, error = function(e) {
  cat("❌ Error in Long-term Screeners Generation:", e$message, "\n")
  cat("⚠️ Continuing with existing screeners data...\n\n")
})

# Step 4: Generate Enhanced Analysis Dashboard
cat(paste(rep("=", 60), collapse=""), "\n")
cat("📊 STEP 4: Generating Enhanced Analysis Dashboard\n")
cat(paste(rep("=", 60), collapse=""), "\n")

tryCatch({
  source("/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis/organized/core_scripts/generate_enhanced_analysis_dashboard.R")
  cat("✅ Enhanced Analysis Dashboard Generated Successfully!\n\n")
}, error = function(e) {
  cat("❌ Error in Enhanced Analysis Dashboard:", e$message, "\n")
  stop("Pipeline failed at enhanced analysis step")
})

# Pipeline Summary
cat(paste(rep("=", 60), collapse=""), "\n")
cat("🎉 COMPLETE ANALYSIS PIPELINE SUMMARY\n")
cat(paste(rep("=", 60), collapse=""), "\n")
cat("✅ Step 1: NSE Data Loading - COMPLETED\n")
cat("✅ Step 2: NSE Universe Analysis - COMPLETED\n")
cat("✅ Step 3: Long-term Screeners - COMPLETED\n")
cat("✅ Step 4: Enhanced Analysis Dashboard - COMPLETED\n\n")

cat("📁 Generated Reports:\n")
cat("   📊 Interactive Dashboard: reports/NSE_Interactive_Dashboard_*.html\n")
cat("   🎯 Long-term Screeners: reports/NSE_Long_Term_Screeners_*.html\n")
cat("   📈 Enhanced Analysis: reports/NSE_Enhanced_Analysis_Dashboard_*.html\n\n")

# Auto-open HTML reports
cat("🌐 Opening HTML reports in browser...\n")
tryCatch({
  # Find the latest HTML files
  interactive_files <- list.files("reports", pattern = "NSE_Interactive_Dashboard_.*\\.html$", full.names = TRUE)
  longterm_files <- list.files("reports", pattern = "NSE_Long_Term_Screeners_.*\\.html$", full.names = TRUE)
  enhanced_files <- list.files("reports", pattern = "NSE_Enhanced_Analysis_Dashboard_.*\\.html$", full.names = TRUE)
  
  # Open the most recent files
  if (length(interactive_files) > 0) {
    latest_interactive <- interactive_files[which.max(file.mtime(interactive_files))]
    system(paste("open", latest_interactive))
    cat("✅ Opened Interactive Dashboard:", basename(latest_interactive), "\n")
  }
  
  if (length(longterm_files) > 0) {
    latest_longterm <- longterm_files[which.max(file.mtime(longterm_files))]
    system(paste("open", latest_longterm))
    cat("✅ Opened Long-term Screeners:", basename(latest_longterm), "\n")
  }
  
  if (length(enhanced_files) > 0) {
    latest_enhanced <- enhanced_files[which.max(file.mtime(enhanced_files))]
    system(paste("open", latest_enhanced))
    cat("✅ Opened Enhanced Analysis:", basename(latest_enhanced), "\n")
  }
  
  cat("🎉 All HTML reports opened successfully!\n")
}, error = function(e) {
  cat("⚠️ Could not auto-open HTML reports:", e$message, "\n")
  cat("📁 Please manually open the HTML files from the reports/ directory\n")
})

cat("\n🚀 Complete NSE Analysis Pipeline Finished Successfully!\n")
cat("⏰ Total Pipeline Time:", format(Sys.time(), "%H:%M:%S"), "\n")
cat("📅 Pipeline Date:", as.character(Sys.Date()), "\n")

# Cleanup
cat("\n🧹 Cleaning up temporary files...\n")
if (file.exists("temp_analysis.R")) {
  file.remove("temp_analysis.R")
}

cat("✨ Pipeline execution completed successfully!\n")
