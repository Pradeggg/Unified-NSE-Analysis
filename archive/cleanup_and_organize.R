# =============================================================================
# CLEANUP AND ORGANIZATION SCRIPT
# =============================================================================
# This script cleans up the project and organizes important files

library(dplyr)
library(lubridate)

# =============================================================================
# FUNCTIONS
# =============================================================================

# Function to create organized directory structure
create_organized_structure <- function() {
  cat("Creating organized directory structure...\n")
  
  # Create main directories
  dirs <- c(
    "organized/",
    "organized/core_scripts/",
    "organized/analysis_results/",
    "organized/backtesting_results/",
    "organized/reports/",
    "organized/data/",
    "organized/documentation/",
    "organized/archive/"
  )
  
  for(dir in dirs) {
    if(!dir.exists(dir)) {
      dir.create(dir, recursive = TRUE)
      cat("✓ Created directory:", dir, "\n")
    }
  }
}

# Function to identify and copy important files
copy_important_files <- function() {
  cat("\nCopying important files to organized structure...\n")
  
  # Core scripts to keep
  core_scripts <- c(
    "fixed_nse_universe_analysis.R",
    "complete_integrated_analysis.R",
    "backtesting_engine.R",
    "run_backtesting_on_latest.R",
    "config.R",
    "main.R"
  )
  
  # Copy core scripts
  for(script in core_scripts) {
    if(file.exists(script)) {
      file.copy(script, paste0("organized/core_scripts/", script))
      cat("✓ Copied core script:", script, "\n")
    }
  }
  
  # Copy latest analysis results
  analysis_files <- list.files("reports", pattern = "comprehensive_nse_enhanced_.*\\.csv", full.names = TRUE)
  if(length(analysis_files) > 0) {
    latest_analysis <- analysis_files[order(file.info(analysis_files)$mtime, decreasing = TRUE)[1]]
    file.copy(latest_analysis, "organized/analysis_results/latest_comprehensive_analysis.csv")
    cat("✓ Copied latest analysis results\n")
  }
  
  # Copy latest backtesting results
  backtesting_files <- list.files("output/backtesting_results", pattern = "integrated_backtesting_results_.*\\.csv", full.names = TRUE)
  if(length(backtesting_files) > 0) {
    latest_backtesting <- backtesting_files[order(file.info(backtesting_files)$mtime, decreasing = TRUE)[1]]
    file.copy(latest_backtesting, "organized/backtesting_results/latest_backtesting_results.csv")
    cat("✓ Copied latest backtesting results\n")
  }
  
  # Copy latest HTML dashboard
  html_files <- list.files("reports", pattern = "NSE_Interactive_Dashboard_.*\\.html", full.names = TRUE)
  if(length(html_files) > 0) {
    latest_html <- html_files[order(file.info(html_files)$mtime, decreasing = TRUE)[1]]
    file.copy(latest_html, "organized/reports/latest_dashboard.html")
    cat("✓ Copied latest HTML dashboard\n")
  }
  
  # Copy latest markdown report
  md_files <- list.files("reports", pattern = "NSE_Analysis_Report_.*\\.md", full.names = TRUE)
  if(length(md_files) > 0) {
    latest_md <- md_files[order(file.info(md_files)$mtime, decreasing = TRUE)[1]]
    file.copy(latest_md, "organized/reports/latest_analysis_report.md")
    cat("✓ Copied latest markdown report\n")
  }
  
  # Copy important data files
  data_files <- c(
    "company_names_mapping.csv",
    "fundamental_scores_database.csv"
  )
  
  for(data_file in data_files) {
    if(file.exists(data_file)) {
      file.copy(data_file, paste0("organized/data/", data_file))
      cat("✓ Copied data file:", data_file, "\n")
    }
  }
  
  # Copy documentation
  doc_files <- c(
    "README.md",
    "BACKTESTING_SYSTEM_OVERVIEW.md"
  )
  
  for(doc_file in doc_files) {
    if(file.exists(doc_file)) {
      file.copy(doc_file, paste0("organized/documentation/", doc_file))
      cat("✓ Copied documentation:", doc_file, "\n")
    }
  }
}

# Function to archive old files
archive_old_files <- function() {
  cat("\nArchiving old files...\n")
  
  # Archive old reports (keep only latest 3)
  report_files <- list.files("reports", full.names = TRUE)
  if(length(report_files) > 3) {
    # Sort by modification time
    sorted_files <- report_files[order(file.info(report_files)$mtime, decreasing = TRUE)]
    files_to_archive <- sorted_files[4:length(sorted_files)]
    
    for(file in files_to_archive) {
      file.copy(file, paste0("organized/archive/", basename(file)))
      cat("✓ Archived:", basename(file), "\n")
    }
  }
  
  # Archive old backtesting results (keep only latest 2)
  backtesting_files <- list.files("output/backtesting_results", full.names = TRUE)
  if(length(backtesting_files) > 2) {
    sorted_files <- backtesting_files[order(file.info(backtesting_files)$mtime, decreasing = TRUE)]
    files_to_archive <- sorted_files[3:length(sorted_files)]
    
    for(file in files_to_archive) {
      file.copy(file, paste0("organized/archive/", basename(file)))
      cat("✓ Archived:", basename(file), "\n")
    }
  }
}

# Function to create cleanup summary
create_cleanup_summary <- function() {
  cat("\nCreating cleanup summary...\n")
  
  timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
  
  summary_content <- paste0(
    "# 🧹 PROJECT CLEANUP AND ORGANIZATION SUMMARY\n",
    "**Cleanup Date:** ", Sys.Date(), " | **Generated:** ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n",
    
    "## 📁 Organized Directory Structure\n\n",
    "```\n",
    "organized/\n",
    "├── core_scripts/          # Essential R scripts\n",
    "├── analysis_results/      # Latest analysis outputs\n",
    "├── backtesting_results/   # Latest backtesting outputs\n",
    "├── reports/              # Latest HTML and markdown reports\n",
    "├── data/                 # Important data files\n",
    "├── documentation/        # Project documentation\n",
    "└── archive/             # Archived old files\n",
    "```\n\n",
    
    "## 📋 Important Files Preserved\n\n",
    "### Core Scripts:\n",
    "- `fixed_nse_universe_analysis.R` - Main analysis engine\n",
    "- `complete_integrated_analysis.R` - Complete workflow\n",
    "- `backtesting_engine.R` - Backtesting engine\n",
    "- `run_backtesting_on_latest.R` - Quick backtesting\n",
    "- `config.R` - Configuration settings\n",
    "- `main.R` - Main entry point\n\n",
    
    "### Latest Results:\n",
    "- `latest_comprehensive_analysis.csv` - Most recent stock analysis\n",
    "- `latest_backtesting_results.csv` - Most recent backtesting results\n",
    "- `latest_dashboard.html` - Most recent interactive dashboard\n",
    "- `latest_analysis_report.md` - Most recent markdown report\n\n",
    
    "### Data Files:\n",
    "- `company_names_mapping.csv` - Company name mappings\n",
    "- `fundamental_scores_database.csv` - Fundamental data\n\n",
    
    "### Documentation:\n",
    "- `README.md` - Project overview\n",
    "- `BACKTESTING_SYSTEM_OVERVIEW.md` - Backtesting documentation\n\n",
    
    "## 🗂️ Files Archived\n\n",
    "Old reports and backtesting results have been moved to the `archive/` directory to reduce clutter while preserving historical data.\n\n",
    
    "## 🚀 Quick Start Guide\n\n",
    "### To run the complete analysis:\n",
    "```r\n",
    "source('organized/core_scripts/complete_integrated_analysis.R')\n",
    "run_complete_integrated_analysis()\n",
    "```\n\n",
    
    "### To run backtesting on latest results:\n",
    "```r\n",
    "source('organized/core_scripts/run_backtesting_on_latest.R')\n",
    "```\n\n",
    
    "### To view latest results:\n",
    "- **Interactive Dashboard:** `organized/reports/latest_dashboard.html`\n",
    "- **Analysis Report:** `organized/reports/latest_analysis_report.md`\n",
    "- **Analysis Data:** `organized/analysis_results/latest_comprehensive_analysis.csv`\n",
    "- **Backtesting Results:** `organized/backtesting_results/latest_backtesting_results.csv`\n\n",
    
    "## 📊 Project Statistics\n\n",
    "- **Total Files Organized:** ", length(list.files("organized", recursive = TRUE)), "\n",
    "- **Core Scripts:** ", length(list.files("organized/core_scripts")), "\n",
    "- **Analysis Results:** ", length(list.files("organized/analysis_results")), "\n",
    "- **Backtesting Results:** ", length(list.files("organized/backtesting_results")), "\n",
    "- **Reports:** ", length(list.files("organized/reports")), "\n",
    "- **Data Files:** ", length(list.files("organized/data")), "\n",
    "- **Documentation:** ", length(list.files("organized/documentation")), "\n",
    "- **Archived Files:** ", length(list.files("organized/archive")), "\n\n",
    
    "---\n",
    "**Cleanup completed successfully!** The project is now organized and ready for efficient use.\n"
  )
  
  # Save summary
  summary_file <- paste0("organized/cleanup_summary_", timestamp, ".md")
  writeLines(summary_content, summary_file)
  
  cat("✓ Cleanup summary saved to:", summary_file, "\n")
  
  return(summary_file)
}

# Function to remove temporary files (optional)
remove_temporary_files <- function() {
  cat("\nRemoving temporary files...\n")
  
  # Files to remove (be careful with this)
  temp_patterns <- c(
    "*.RData",
    "*.tmp",
    ".DS_Store"
  )
  
  # Only remove .DS_Store files for now (safe)
  ds_store_files <- list.files(pattern = ".DS_Store", recursive = TRUE, full.names = TRUE)
  if(length(ds_store_files) > 0) {
    file.remove(ds_store_files)
    cat("✓ Removed", length(ds_store_files), ".DS_Store files\n")
  }
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

cat("Starting project cleanup and organization...\n")
cat("============================================================\n")

# Create organized structure
create_organized_structure()

# Copy important files
copy_important_files()

# Archive old files
archive_old_files()

# Create cleanup summary
summary_file <- create_cleanup_summary()

# Remove temporary files (optional)
remove_temporary_files()

# Print final summary
cat("\n" , "=", 60, "\n")
cat("PROJECT CLEANUP AND ORGANIZATION COMPLETED\n")
cat("=", 60, "\n")

cat("\n📁 ORGANIZED STRUCTURE CREATED:\n")
cat("organized/\n")
cat("├── core_scripts/          # Essential R scripts\n")
cat("├── analysis_results/      # Latest analysis outputs\n")
cat("├── backtesting_results/   # Latest backtesting outputs\n")
cat("├── reports/              # Latest HTML and markdown reports\n")
cat("├── data/                 # Important data files\n")
cat("├── documentation/        # Project documentation\n")
cat("└── archive/             # Archived old files\n")

cat("\n🎯 QUICK START:\n")
cat("1. View latest dashboard: organized/reports/latest_dashboard.html\n")
cat("2. Run complete analysis: source('organized/core_scripts/complete_integrated_analysis.R')\n")
cat("3. Run backtesting: source('organized/core_scripts/run_backtesting_on_latest.R')\n")

cat("\n📊 STATISTICS:\n")
cat("Total files organized:", length(list.files("organized", recursive = TRUE)), "\n")
cat("Core scripts:", length(list.files("organized/core_scripts")), "\n")
cat("Analysis results:", length(list.files("organized/analysis_results")), "\n")
cat("Backtesting results:", length(list.files("organized/backtesting_results")), "\n")
cat("Reports:", length(list.files("organized/reports")), "\n")
cat("Data files:", length(list.files("organized/data")), "\n")
cat("Documentation:", length(list.files("organized/documentation")), "\n")
cat("Archived files:", length(list.files("organized/archive")), "\n")

cat("\n" , "=", 60, "\n")
cat("✅ Project cleanup and organization completed successfully!\n")
cat("Check organized/ directory for clean, organized structure.\n")
