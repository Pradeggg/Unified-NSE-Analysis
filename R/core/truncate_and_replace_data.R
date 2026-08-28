#!/usr/bin/env Rscript

# =============================================================================
# Truncate and Replace NSE Data
# =============================================================================

cat("=== TRUNCATING AND REPLACING EXISTING DATA ===\n")

# Backup existing data
cat("Backing up existing data...\n")
if(file.exists("nse_sec_full_data.csv")) {
  backup_name <- paste0("nse_sec_full_data_backup_", format(Sys.time(), "%Y%m%d_%H%M%S"), ".csv")
  file.rename("nse_sec_full_data.csv", backup_name)
  cat("✓ Backup created:", backup_name, "\n")
} else {
  cat("⚠ No existing data file found\n")
}

# Load fresh historical data
cat("\nLoading fresh historical data...\n")
source("../getdataNSE.R")
fresh_data <- get_nse_full_data("2023-01-01")

# Write fresh data
cat("\n=== WRITING FRESH DATA ===\n")
write.csv(fresh_data, "nse_sec_full_data.csv", row.names = FALSE)
cat("✓ Fresh data written to nse_sec_full_data.csv\n")
cat("Total records:", nrow(fresh_data), "\n")
cat("Date range:", as.character(min(fresh_data$TIMESTAMP)), "to", as.character(max(fresh_data$TIMESTAMP)), "\n")

# Verify Tata Steel is included
cat("\n=== VERIFYING TATA STEEL ===\n")
tata_steel <- fresh_data[fresh_data$SYMBOL == "TATASTEEL", ]
if(nrow(tata_steel) > 0) {
  cat("✓ Tata Steel found in fresh data!\n")
  cat("Latest record date:", as.character(max(tata_steel$TIMESTAMP)), "\n")
  cat("Total Tata Steel records:", nrow(tata_steel), "\n")
} else {
  cat("❌ Tata Steel not found in fresh data\n")
}

cat("\n=== DATA REPLACEMENT COMPLETED ===\n")
