#!/usr/bin/env Rscript
# Fetch fundamental scores from Screener.in for a list of symbols and merge into
# fundamental_scores_database.csv. Usage:
#   Rscript fetch_screener_fundamentals.R [symbols_file] [fund_csv_path]
# If no args: symbols_file = working-sector/output/symbols_to_fetch.txt,
#             fund_csv_path = organized/data/fundamental_scores_database.csv
# Run from project root.

suppressMessages({
  library(dplyr)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) args <- character(0)

# Paths: assume run from project root
PROJECT_ROOT <- getwd()
if (basename(PROJECT_ROOT) == "working-sector") PROJECT_ROOT <- dirname(PROJECT_ROOT)

SYMBOLS_FILE <- if (length(args) >= 1) args[1] else file.path(PROJECT_ROOT, "working-sector", "output", "symbols_to_fetch.txt")
FUND_CSV    <- if (length(args) >= 2) args[2] else file.path(PROJECT_ROOT, "organized", "data", "fundamental_scores_database.csv")

if (!file.exists(SYMBOLS_FILE)) {
  message("No symbols file found: ", SYMBOLS_FILE)
  quit(save = "no", status = 0)
}

symbols_to_fetch <- trimws(readLines(SYMBOLS_FILE))
symbols_to_fetch <- symbols_to_fetch[nzchar(symbols_to_fetch)]
if (length(symbols_to_fetch) == 0) {
  message("No symbols to fetch.")
  quit(save = "no", status = 0)
}

# Source screener functions
screener_path <- file.path(PROJECT_ROOT, "core", "screenerdata.R")
if (!file.exists(screener_path)) {
  stop("screenerdata.R not found at ", screener_path)
}
source(screener_path)
if (!exists("fn_get_enhanced_fund_score")) {
  stop("fn_get_enhanced_fund_score not found in screenerdata.R")
}

# Load existing scores
existing_scores <- data.frame()
if (file.exists(FUND_CSV)) {
  existing_scores <- read.csv(FUND_CSV, stringsAsFactors = FALSE)
  existing_symbols <- unique(toupper(trimws(existing_scores$symbol)))
  symbols_to_fetch <- setdiff(toupper(trimws(symbols_to_fetch)), existing_symbols)
  if (length(symbols_to_fetch) == 0) {
    message("All symbols already have fundamental scores.")
    quit(save = "no", status = 0)
  }
}

required_columns <- c("symbol", "ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "SALES_GROWTH",
                      "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING", "processed_date",
                      "processing_batch", "batch_number")

message("Fetching fundamentals from Screener.in for ", length(symbols_to_fetch), " symbols...")
batch <- format(Sys.time(), "%Y%m%d_%H%M")
new_list <- list()
success <- 0
fail <- 0

for (i in seq_along(symbols_to_fetch)) {
  sym <- symbols_to_fetch[i]
  message(sprintf("[%d/%d] %s", i, length(symbols_to_fetch), sym))
  Sys.sleep(0.8)
  res <- tryCatch({
    out <- fn_get_enhanced_fund_score(sym)
    if (is.null(out) || nrow(out) == 0) NULL else out
  }, error = function(e) NULL)
  if (!is.null(res) && nrow(res) > 0 && "ENHANCED_FUND_SCORE" %in% names(res)) {
    res$symbol <- sym
    res$processed_date <- Sys.Date()
    res$processing_batch <- batch
    res$batch_number <- 1L
    for (col in setdiff(required_columns, names(res))) {
      if (col %in% c("ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "SALES_GROWTH", "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING"))
        res[[col]] <- 50
      else if (col == "symbol") res[[col]] <- sym
      else if (col == "processed_date") res[[col]] <- Sys.Date()
      else if (col == "processing_batch") res[[col]] <- batch
      else if (col == "batch_number") res[[col]] <- 1L
      else res[[col]] <- NA
    }
    res <- res[, required_columns, drop = FALSE]
    new_list[[sym]] <- res
    success <- success + 1
  } else {
    fail <- fail + 1
    new_list[[sym]] <- data.frame(
      symbol = sym,
      ENHANCED_FUND_SCORE = 50,
      EARNINGS_QUALITY = 50,
      SALES_GROWTH = 50,
      FINANCIAL_STRENGTH = 50,
      INSTITUTIONAL_BACKING = 50,
      processed_date = Sys.Date(),
      processing_batch = batch,
      batch_number = 1L,
      stringsAsFactors = FALSE
    )
  }
}

if (length(new_list) == 0) {
  message("No new scores to write.")
  quit(save = "no", status = 0)
}

new_df <- do.call(rbind, new_list)
rownames(new_df) <- NULL

# Merge with existing: keep existing rows, add new, then dedupe by symbol (keep latest)
if (nrow(existing_scores) > 0) {
  for (col in setdiff(required_columns, names(existing_scores)))
    existing_scores[[col]] <- NA
  existing_scores <- existing_scores[, intersect(names(existing_scores), required_columns), drop = FALSE]
  combined <- rbind(existing_scores, new_df)
} else {
  combined <- new_df
}
combined <- combined %>%
  mutate(processed_date = as.Date(processed_date, origin = "1970-01-01")) %>%
  arrange(symbol, desc(processed_date)) %>%
  distinct(symbol, .keep_all = TRUE)

out_dir <- dirname(FUND_CSV)
if (!dir.exists(out_dir)) dir.create(out_dir, recursive = TRUE)
write.csv(combined, FUND_CSV, row.names = FALSE)
message("Wrote ", nrow(combined), " rows to ", FUND_CSV, " (success: ", success, ", default: ", fail, ")")
