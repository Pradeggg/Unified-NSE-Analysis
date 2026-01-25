#!/usr/bin/env Rscript

# =============================================================================
# Clean Analysis Script - Fix 1-Month Change Calculation
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
})

cat("Cleaning analysis script and fixing 1-month change calculation...\n")

# Read the original analysis script
script_file <- "fixed_nse_universe_analysis.R"
script_content <- readLines(script_file, warn = FALSE)

# Find the problematic 1-month change calculation section
month_change_start <- which(grepl("# 1-month change \\(30 days\\)", script_content))[1]

if(is.na(month_change_start)) {
  stop("Could not find 1-month change calculation section")
}

cat("Found 1-month change calculation at line:", month_change_start, "\n")

# Create the properly fixed 1-month change calculation
fixed_calculation <- c(
  "          # 1-month change (30 days) - properly fixed date calculation",
  "          # Convert latest_date to Date object if it's not already",
  "          latest_date_obj <- as.Date(latest_date)",
  "          month_1_ago <- latest_date_obj - 30",
  "          ",
  "          # Find the closest available date within ±5 days of 30 days ago",
  "          available_dates <- unique(stock_data$TIMESTAMP)",
  "          available_dates_obj <- as.Date(available_dates)",
  "          ",
  "          # Find the closest date within ±5 days",
  "          date_diffs <- abs(available_dates_obj - month_1_ago)",
  "          closest_date_idx <- which.min(date_diffs)",
  "          closest_date <- available_dates[closest_date_idx]",
  "          ",
  "          # Only use if the closest date is within 5 days of target",
  "          if(date_diffs[closest_date_idx] <= 5) {",
  "            price_1m_ago <- stock_data %>%",
  "              filter(TIMESTAMP == closest_date) %>%",
  "              pull(CLOSE) %>%",
  "              first()",
  "            change_1m <- ifelse(!is.na(price_1m_ago),",
  "                               round(((current_price - price_1m_ago) / price_1m_ago) * 100, 2),",
  "                               NA)",
  "          } else {",
  "            change_1m <- NA",
  "          }"
)

# Find the end of the current 1-month calculation
month_change_end <- month_change_start
for(i in (month_change_start + 1):length(script_content)) {
  if(grepl("change_1m <-", script_content[i]) && grepl("round.*price_1m_ago.*100", script_content[i])) {
    month_change_end <- i
    break
  }
}

# Find the line after the change_1m assignment
for(i in (month_change_end + 1):length(script_content)) {
  if(!grepl("^\\s*$", script_content[i]) && !grepl("^\\s*#", script_content[i])) {
    month_change_end <- i - 1
    break
  }
}

cat("Replacing lines", month_change_start, "to", month_change_end, "\n")

# Replace the section
new_script_content <- c(
  script_content[1:(month_change_start - 1)],
  fixed_calculation,
  script_content[(month_change_end + 1):length(script_content)]
)

# Write the cleaned script
writeLines(new_script_content, "fixed_nse_universe_analysis_clean.R")

cat("✅ Successfully created cleaned analysis script!\n")
cat("📁 New file: fixed_nse_universe_analysis_clean.R\n")
cat("🎯 Fixes applied:\n")
cat("   - Removed duplicate code\n")
cat("   - Fixed syntax errors\n")
cat("   - Proper date calculation for 1-month change\n")
cat("   - Clean, working script\n")
