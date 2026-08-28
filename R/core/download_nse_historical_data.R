#!/usr/bin/env Rscript

# =============================================================================
# Download & Build Historical NSE Securities File: data/nse_sec_full_data.csv
# =============================================================================
# - Pulls daily bhavcopy-style equity data from NSE website for a date range
# - Appends/merges into a single, deduplicated historical file
# - Output is compatible with:
#   - load_latest_data.R (expects data/nse_sec_full_data.csv)
#   - fixed_nse_universe_analysis.py
# =============================================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(lubridate)
  library(httr)
})

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

get_project_root <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    return(dirname(normalizePath(sub("^--file=", "", file_arg[1]))))
  }
  if (!is.null(sys.frames()[[1]]$ofile)) {
    return(dirname(normalizePath(sys.frames()[[1]]$ofile)))
  }
  getwd()
}

PROJECT_ROOT <- get_project_root()
setwd(PROJECT_ROOT)

DATA_DIR <- file.path(PROJECT_ROOT, "data")
if (!dir.exists(DATA_DIR)) dir.create(DATA_DIR, recursive = TRUE)

HIST_FILE <- file.path(DATA_DIR, "nse_sec_full_data.csv")

# NSE bhavcopy URL pattern (equities)
# This pattern often works, but NSE may change it; keep configurable.
NSE_BHAV_URL <- function(d) {
  # d is Date; NSE bhavcopy usually: CM<DD><MMM><YYYY>BHAV.csv.zip
  # Example: https://archives.nseindia.com/content/historical/EQUITIES/2026/JAN/cm01JAN2026bhav.csv.zip
  yyyy <- format(d, "%Y")
  mon  <- toupper(format(d, "%b"))
  dd   <- format(d, "%d")
  sprintf(
    "https://archives.nseindia.com/content/historical/EQUITIES/%s/%s/cm%s%s%sbhav.csv.zip",
    yyyy, mon, dd, mon, yyyy
  )
}

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

download_bhavcopy_for_date <- function(d, temp_dir) {
  url <- NSE_BHAV_URL(d)
  cat("Downloading bhavcopy for", as.character(d), "from:\n  ", url, "\n")
  
  resp <- tryCatch(
    {
      GET(url, add_headers(`User-Agent` = "Mozilla/5.0"))
    },
    error = function(e) {
      cat("  ❌ HTTP error:", e$message, "\n")
      return(NULL)
    }
  )
  
  if (is.null(resp) || http_error(resp)) {
    cat("  ❌ Failed (HTTP status:", if (!is.null(resp)) status_code(resp) else "NA", ")\n")
    return(NULL)
  }
  
  zip_path <- file.path(temp_dir, paste0("bhav_", format(d, "%Y%m%d"), ".zip"))
  writeBin(content(resp, "raw"), zip_path)
  
  # Unzip and read CSV
  files <- utils::unzip(zip_path, exdir = temp_dir)
  csv_file <- files[grep("\\.csv$", files, ignore.case = TRUE)][1]
  if (is.na(csv_file)) {
    cat("  ❌ No CSV in bhavcopy ZIP for", as.character(d), "\n")
    return(NULL)
  }
  
  cat("  ✓ Downloaded and extracted:", basename(csv_file), "\n")
  
  # Bhavcopy columns: SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE,
  # TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN
  df <- tryCatch(
    {
      read_csv(csv_file, show_col_types = FALSE)
    },
    error = function(e) {
      cat("  ❌ Error reading CSV:", e$message, "\n")
      return(NULL)
    }
  )
  
  if (is.null(df) || !"SYMBOL" %in% names(df) || !"TIMESTAMP" %in% names(df)) {
    cat("  ❌ Unexpected CSV structure for", as.character(d), "\n")
    return(NULL)
  }
  
  df <- df %>%
    mutate(
      TIMESTAMP = as.Date(TIMESTAMP, format = "%d-%b-%Y")
    ) %>%
    filter(!is.na(SYMBOL), SYMBOL != "", !is.na(TIMESTAMP))
  
  cat("  ✓ Rows loaded:", nrow(df), "\n")
  df
}

build_or_update_historical_file <- function(start_date, end_date) {
  if (start_date > end_date) {
    stop("start_date must be <= end_date")
  }
  
  cat("=== BUILDING / UPDATING NSE HISTORICAL SECURITIES FILE ===\n")
  cat("Project root :", PROJECT_ROOT, "\n")
  cat("Data dir     :", DATA_DIR, "\n")
  cat("Output file  :", HIST_FILE, "\n")
  cat("Date range   :", as.character(start_date), "to", as.character(end_date), "\n\n")
  
  existing <- NULL
  if (file.exists(HIST_FILE)) {
    cat("Loading existing historical file...\n")
    existing <- read_csv(HIST_FILE, show_col_types = FALSE)
    if (!"TIMESTAMP" %in% names(existing)) {
      stop("Existing nse_sec_full_data.csv has no TIMESTAMP column.")
    }
    existing <- existing %>%
      mutate(TIMESTAMP = as.Date(TIMESTAMP))
    cat("  ✓ Existing rows:", nrow(existing), "\n")
  }
  
  all_dates <- seq.Date(start_date, end_date, by = "day")
  temp_dir <- tempdir()
  
  new_data_list <- list()
  for (d in all_dates) {
    # Skip non-trading days quickly if already in existing
    if (!is.null(existing) && any(existing$TIMESTAMP == d)) {
      cat("Skipping", as.character(d), "- already in existing file\n")
      next
    }
    
    day_df <- download_bhavcopy_for_date(d, temp_dir)
    if (!is.null(day_df) && nrow(day_df) > 0) {
      new_data_list[[as.character(d)]] <- day_df
    }
  }
  
  if (length(new_data_list) == 0 && !is.null(existing)) {
    cat("\nNo new data downloaded; existing file is already up to date for this range.\n")
    return(invisible(existing))
  }
  
  new_data <- if (length(new_data_list) > 0) bind_rows(new_data_list) else NULL
  
  combined <- if (!is.null(existing) && !is.null(new_data)) {
    bind_rows(existing, new_data)
  } else if (!is.null(existing)) {
    existing
  } else {
    new_data
  }
  
  if (is.null(combined) || nrow(combined) == 0) {
    stop("No data available to write to nse_sec_full_data.csv")
  }
  
  # Deduplicate (keep latest TOTTRDVAL per SYMBOL/TIMESTAMP)
  combined <- combined %>%
    arrange(SYMBOL, TIMESTAMP, desc(TOTTRDVAL)) %>%
    distinct(SYMBOL, TIMESTAMP, .keep_all = TRUE) %>%
    arrange(TIMESTAMP, SYMBOL)
  
  write_csv(combined, HIST_FILE)
  
  cat("\n=== SUMMARY ===\n")
  cat("Total rows written :", nrow(combined), "\n")
  cat("Date range         :", as.character(min(combined$TIMESTAMP)), "to", as.character(max(combined$TIMESTAMP)), "\n")
  cat("Unique symbols     :", length(unique(combined$SYMBOL)), "\n")
  cat("File               :", HIST_FILE, "\n")
  cat("✅ Historical NSE securities file is ready.\n")
  
  invisible(combined)
}

# ---------------------------------------------------------------------------
# Main (when run as a script)
# ---------------------------------------------------------------------------

if (sys.nframe() == 0) {
  # Default: last 60 calendar days; adjust as needed
  end_date_default <- Sys.Date()
  start_date_default <- end_date_default - 60
  
  cat("Running download_nse_historical_data.R as a script.\n")
  cat("Default range: last 60 days (", as.character(start_date_default), "to", as.character(end_date_default), ")\n\n")
  
  build_or_update_historical_file(start_date_default, end_date_default)
}

