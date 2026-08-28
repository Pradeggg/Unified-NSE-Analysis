#!/usr/bin/env Rscript

# =============================================================================
# Final Data Merge - August 26 to September 1, 2025
# =============================================================================

cat("=== FINAL DATA MERGE - AUGUST 26 TO SEPTEMBER 1, 2025 ===\n")

# Load the getdataNSE functions
source("../getdataNSE.R")

# Load the final stretch of data
cat("Loading final data from August 26 to September 1, 2025...\n")
final_data <- get_nse_full_data("2025-08-26")

# Read existing complete dataset
cat("Reading existing complete dataset...\n")
existing_data <- read.csv("nse_sec_full_data.csv", stringsAsFactors = FALSE)

# Combine existing and new data
cat("Merging data...\n")
all_data <- rbind(existing_data, final_data)

# Remove duplicates and clean data
cat("Cleaning and deduplicating data...\n")
all_data_clean <- all_data %>%
  filter(!is.na(SYMBOL) & SYMBOL != "" & !is.na(CLOSE) & CLOSE > 0) %>%
  distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE) %>%
  group_by(SYMBOL, TIMESTAMP) %>%
  slice_max(TOTTRDVAL, n = 1, with_ties = FALSE) %>%
  ungroup()

# Write the final complete dataset
cat("Writing final complete dataset...\n")
write.csv(all_data_clean, "nse_sec_full_data.csv", row.names = FALSE)

# Summary
cat("\n=== FINAL COMPLETE DATASET SUMMARY ===\n")
cat("Total records:", nrow(all_data_clean), "\n")
cat("Date range:", as.character(min(all_data_clean$TIMESTAMP)), "to", as.character(max(all_data_clean$TIMESTAMP)), "\n")
cat("Unique symbols:", length(unique(all_data_clean$SYMBOL)), "\n")

# Verify Tata Steel
cat("\n=== VERIFYING TATA STEEL ===\n")
tata_steel <- all_data_clean[all_data_clean$SYMBOL == "TATASTEEL", ]
if(nrow(tata_steel) > 0) {
  cat("✓ Tata Steel found in final dataset!\n")
  cat("Latest record date:", as.character(max(tata_steel$TIMESTAMP)), "\n")
  cat("Total Tata Steel records:", nrow(tata_steel), "\n")
  cat("Latest close price:", tata_steel$CLOSE[which.max(tata_steel$TIMESTAMP)], "\n")
} else {
  cat("❌ Tata Steel not found in final dataset\n")
}

# Check latest available dates
cat("\n=== LATEST DATA VERIFICATION ===\n")
latest_dates <- sort(unique(all_data_clean$TIMESTAMP), decreasing = TRUE)[1:5]
cat("Latest 5 available dates:\n")
for(date in latest_dates) {
  count <- sum(all_data_clean$TIMESTAMP == date)
  cat("  ", as.character(date), ":", count, "records\n")
}

cat("\n=== FINAL DATA MERGE COMPLETED SUCCESSFULLY ===\n")

