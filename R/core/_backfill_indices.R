# PG-indices: targeted backfill of missing index trading days.
# Reads functions from load_latest_nse_data_comprehensive.R but skips its top-level
# `cat(...)` chatter and any setwd to keep cwd stable.
suppressMessages({library(dplyr); library(httr)})

src <- readLines("load_latest_nse_data_comprehensive.R")
end_funcs <- grep("^# Main Execution", src)[1]
fn_lines <- src[1:(end_funcs - 1)]
fn_lines <- fn_lines[!grepl("^setwd", fn_lines)]
fn_lines <- fn_lines[!grepl("^cat\\(", fn_lines)]
eval(parse(text = paste(fn_lines, collapse = "\n")))

target_file <- "data/nse_index_data.csv"
existing <- read.csv(target_file, stringsAsFactors = FALSE)
existing_dates <- sort(unique(as.character(existing$TIMESTAMP)))
cat("Existing rows:", nrow(existing), "  latest:", tail(existing_dates, 1), "\n")

# Try every weekday from latest+1 through today and append whatever NSE gives us.
latest <- max(as.Date(existing$TIMESTAMP), na.rm = TRUE)
today  <- Sys.Date()
candidate_dates <- seq(latest + 1, today, by = "day")
candidate_dates <- candidate_dates[!format(candidate_dates, "%u") %in% c("6", "7")]
cat("Trying:", paste(candidate_dates, collapse = ", "), "\n")

new_chunks <- list()
for (d in as.list(candidate_dates)) {
  chunk <- tryCatch(load_index_data_for_date(d), error = function(e) NULL)
  if (!is.null(chunk) && nrow(chunk) > 0) new_chunks[[as.character(d)]] <- chunk
}

if (length(new_chunks) == 0) {
  cat("No new dates fetched. File unchanged.\n")
} else {
  added <- bind_rows(new_chunks)
  added <- added[, intersect(names(existing), names(added))]
  combined <- rbind(existing[, names(added)], added) %>%
    distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE)
  if (nrow(combined) >= nrow(existing)) {
    write.csv(combined, target_file, row.names = FALSE)
    cat("WROTE rows:", nrow(combined),
        "  latest:", as.character(max(as.Date(combined$TIMESTAMP))), "\n")
  } else {
    cat("REFUSING to write (combined < existing). Aborting.\n")
  }
}
