#!/usr/bin/env Rscript

# =============================================================================
# Update Company Names Mapping from Symbols.tsv
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
})

cat("Starting company names mapping update...\n")

# Read existing company names mapping
existing_mapping <- read_csv("../data/company_names_mapping.csv", 
                           col_types = cols(SYMBOL = col_character(), 
                                          COMPANY_NAME = col_character()))

cat("Loaded existing mapping with", nrow(existing_mapping), "entries\n")

# Read Symbols.tsv file
symbols_data <- read_tsv("../data/Symbols.tsv", 
                        col_names = FALSE,
                        col_types = cols(X1 = col_character(), 
                                       X2 = col_character()))

# Clean the data - remove empty rows and header rows
symbols_data <- symbols_data %>%
  filter(!is.na(X1), 
         !is.na(X2), 
         X1 != "", 
         X2 != "",
         !grepl("^\\s*$", X1),
         !grepl("^\\s*$", X2),
         !grepl("NIFTY", X2, ignore.case = TRUE)) %>%
  rename(SYMBOL = X1, COMPANY_NAME = X2)

cat("Loaded Symbols.tsv with", nrow(symbols_data), "entries after cleaning\n")

# Check for duplicates in existing mapping
existing_duplicates <- existing_mapping %>%
  group_by(SYMBOL) %>%
  filter(n() > 1) %>%
  ungroup()

if(nrow(existing_duplicates) > 0) {
  cat("Warning: Found", nrow(existing_duplicates), "duplicate symbols in existing mapping\n")
  print(existing_duplicates)
}

# Check for duplicates in new symbols data
new_duplicates <- symbols_data %>%
  group_by(SYMBOL) %>%
  filter(n() > 1) %>%
  ungroup()

if(nrow(new_duplicates) > 0) {
  cat("Warning: Found", nrow(new_duplicates), "duplicate symbols in Symbols.tsv\n")
  print(new_duplicates)
}

# Remove duplicates from new data (keep first occurrence)
symbols_data <- symbols_data %>%
  group_by(SYMBOL) %>%
  slice(1) %>%
  ungroup()

# Find symbols that are in Symbols.tsv but not in existing mapping
new_symbols <- symbols_data %>%
  anti_join(existing_mapping, by = "SYMBOL")

cat("Found", nrow(new_symbols), "new symbols to add\n")

# Find symbols that are in existing mapping but not in Symbols.tsv
missing_symbols <- existing_mapping %>%
  anti_join(symbols_data, by = "SYMBOL")

cat("Found", nrow(missing_symbols), "symbols in existing mapping but not in Symbols.tsv\n")

# Find symbols that exist in both but have different company names
common_symbols <- existing_mapping %>%
  inner_join(symbols_data, by = "SYMBOL", suffix = c("_existing", "_new")) %>%
  filter(COMPANY_NAME_existing != COMPANY_NAME_new)

cat("Found", nrow(common_symbols), "symbols with different company names\n")

if(nrow(common_symbols) > 0) {
  cat("Sample differences:\n")
  print(head(common_symbols[, c("SYMBOL", "COMPANY_NAME_existing", "COMPANY_NAME_new")], 10))
}

# Create updated mapping by:
# 1. Keeping all existing entries
# 2. Adding new symbols from Symbols.tsv
# 3. For common symbols, keeping the existing name (to preserve any custom formatting)

updated_mapping <- existing_mapping %>%
  bind_rows(new_symbols) %>%
  arrange(SYMBOL)

cat("Updated mapping now has", nrow(updated_mapping), "entries\n")

# Write the updated mapping back to file
write_csv(updated_mapping, "../data/company_names_mapping.csv")

cat("Successfully updated company_names_mapping.csv\n")

# Summary report
cat("\n=== UPDATE SUMMARY ===\n")
cat("Original entries:", nrow(existing_mapping), "\n")
cat("New entries added:", nrow(new_symbols), "\n")
cat("Total entries after update:", nrow(updated_mapping), "\n")
cat("Symbols with different names:", nrow(common_symbols), "\n")

if(nrow(new_symbols) > 0) {
  cat("\nSample new entries added:\n")
  print(head(new_symbols, 10))
}

cat("\nUpdate completed successfully!\n")
