#!/usr/bin/env Rscript

# =============================================================================
# Merge All Loaded Data into Main Database
# =============================================================================

cat("=== MERGING ALL LOADED DATA INTO MAIN DATABASE ===\n")

# Load the getdataNSE functions
source("../getdataNSE.R")

# Load data from January 2023 to November 2024 (already loaded)
cat("Loading data from January 2023 to November 2024...\n")
data_2023_2024 <- get_nse_full_data("2023-01-01")

# Load data from November 2024 to June 2025
cat("Loading data from November 2024 to June 2025...\n")
data_nov2024_jun2025 <- get_nse_full_data("2024-11-28")

# Load data from June 2025 to August 2025
cat("Loading data from June 2025 to August 2025...\n")
data_jun2025_aug2025 <- get_nse_full_data("2025-06-13")

# Load data from August 2025 to September 2025
cat("Loading data from August 2025 to September 2025...\n")
data_aug2025_sep2025 <- get_nse_full_data("2025-08-08")

# Combine all data
cat("\n=== COMBINING ALL DATA ===\n")
all_data <- rbind(data_2023_2024, data_nov2024_jun2025, data_jun2025_aug2025, data_aug2025_sep2025)

# Remove duplicates and clean data
cat("Cleaning and deduplicating data...\n")
all_data_clean <- all_data %>%
  filter(!is.na(SYMBOL) & SYMBOL != "" & !is.na(CLOSE) & CLOSE > 0) %>%
  distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE) %>%
  group_by(SYMBOL, TIMESTAMP) %>%
  slice_max(TOTTRDVAL, n = 1, with_ties = FALSE) %>%
  ungroup()

# Write the complete dataset
cat("Writing complete dataset...\n")
write.csv(all_data_clean, "nse_sec_full_data.csv", row.names = FALSE)

# Summary
cat("\n=== FINAL DATASET SUMMARY ===\n")
cat("Total records:", nrow(all_data_clean), "\n")
cat("Date range:", as.character(min(all_data_clean$TIMESTAMP)), "to", as.character(max(all_data_clean$TIMESTAMP)), "\n")
cat("Unique symbols:", length(unique(all_data_clean$SYMBOL)), "\n")

# Verify Tata Steel
cat("\n=== VERIFYING TATA STEEL ===\n")
tata_steel <- all_data_clean[all_data_clean$SYMBOL == "TATASTEEL", ]
if(nrow(tata_steel) > 0) {
  cat("✓ Tata Steel found in complete dataset!\n")
  cat("Latest record date:", as.character(max(tata_steel$TIMESTAMP)), "\n")
  cat("Total Tata Steel records:", nrow(tata_steel), "\n")
  cat("Latest close price:", tata_steel$CLOSE[which.max(tata_steel$TIMESTAMP)], "\n")
} else {
  cat("❌ Tata Steel not found in complete dataset\n")
}

cat("\n=== DATA MERGE COMPLETED SUCCESSFULLY ===\n")

