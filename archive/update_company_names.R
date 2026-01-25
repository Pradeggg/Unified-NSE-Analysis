# Script to update company_names_mapping.csv from NSE data
library(dplyr)
library(readr)

cat("Updating company names mapping from NSE data...\n")

# Read the NSE data file
nse_data <- read.csv("reports/Pd290825.csv", stringsAsFactors = FALSE)

# Filter for actual stocks (not indices) - look for rows with SYMBOL and SECURITY
# Remove rows where SYMBOL is empty or SECURITY is empty
stock_data <- nse_data %>%
  filter(!is.na(SYMBOL) & SYMBOL != "" & 
         !is.na(SECURITY) & SECURITY != "" &
         MKT == "N" & SERIES == "EQ") %>%
  select(SYMBOL, SECURITY) %>%
  distinct()

# Clean the data
stock_data$SYMBOL <- trimws(stock_data$SYMBOL)
stock_data$SECURITY <- trimws(stock_data$SECURITY)

# Remove any rows with empty symbols or security names
stock_data <- stock_data %>%
  filter(SYMBOL != "" & SECURITY != "")

# Convert to uppercase for consistency
stock_data$SYMBOL <- toupper(stock_data$SYMBOL)

# Create the mapping dataframe
company_mapping <- data.frame(
  SYMBOL = stock_data$SYMBOL,
  COMPANY_NAME = stock_data$SECURITY,
  stringsAsFactors = FALSE
)

# Remove duplicates
company_mapping <- company_mapping %>%
  distinct(SYMBOL, .keep_all = TRUE)

# Sort by SYMBOL
company_mapping <- company_mapping %>%
  arrange(SYMBOL)

# Save the updated mapping
write.csv(company_mapping, "company_names_mapping.csv", row.names = FALSE)

cat("Company names mapping updated successfully!\n")
cat("Total companies mapped:", nrow(company_mapping), "\n")
cat("Sample mappings:\n")
print(head(company_mapping, 10))

# Show some statistics
cat("\nMapping Statistics:\n")
cat("Total unique symbols:", length(unique(company_mapping$SYMBOL)), "\n")
cat("Total unique company names:", length(unique(company_mapping$COMPANY_NAME)), "\n")

# Check for any symbols with multiple company names
duplicates <- company_mapping %>%
  group_by(SYMBOL) %>%
  filter(n() > 1) %>%
  arrange(SYMBOL)

if(nrow(duplicates) > 0) {
  cat("\nWarning: Found symbols with multiple company names:\n")
  print(duplicates)
} else {
  cat("\nNo duplicate symbols found - mapping is clean!\n")
}
