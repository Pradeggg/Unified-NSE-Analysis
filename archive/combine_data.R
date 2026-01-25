# Combine existing and new data
existing_data <- read.csv('nse_sec_full_data.csv')
new_data <- read.csv('temp_new_data.csv')

cat('Existing records:', nrow(existing_data), '\n')
cat('New records:', nrow(new_data), '\n')

# Fix column mismatch
new_data$ISIN <- NA
new_data <- new_data[, c('SYMBOL', 'ISIN', 'TIMESTAMP', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'LAST', 'PREVCLOSE', 'TOTTRDQTY', 'TOTTRDVAL', 'TOTALTRADES')]

# Combine data
combined_data <- rbind(existing_data, new_data)
combined_data <- combined_data %>% distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)

# Save combined data
write.csv(combined_data, 'nse_sec_full_data.csv', row.names = FALSE)

cat('Combined records:', nrow(combined_data), '\n')
cat('Records added:', nrow(combined_data) - nrow(existing_data), '\n')

# Update audit file
audit <- read.csv('audit.csv')
new_entry <- data.frame(datafile = 'nse_sec_full_data.csv', rows = nrow(combined_data), last_load_dt = as.character(Sys.Date()))
audit <- rbind(audit, new_entry)
write.csv(audit, 'audit.csv', row.names = FALSE)

cat('Audit file updated\n')
