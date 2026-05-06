#!/usr/bin/env Rscript
# Validate 5-year fundamentals output files
# Usage: Rscript validate_5yr_output.R

suppressMessages({
  library(dplyr)
})

PROJECT_ROOT <- getwd()
CACHE_DIR <- file.path(PROJECT_ROOT, "data")

# Expected output files
files <- list(
  quality = file.path(CACHE_DIR, "quality_fundamentals.csv"),
  quarterly = file.path(CACHE_DIR, "quarterly_eps.csv"),
  peers = file.path(CACHE_DIR, "peer_comparisons.csv"),
  cashflow = file.path(CACHE_DIR, "cashflow_data.csv")
)

cat("\n=== Validating 5-Year Fundamentals Output ===\n\n")

all_passed <- TRUE

# Check file existence
for (name in names(files)) {
  path <- files[[name]]
  if (file.exists(path)) {
    cat("✓ ", basename(path), " exists\n", sep = "")
  } else {
    cat("✗ ", basename(path), " MISSING\n", sep = "")
    all_passed <- FALSE
  }
}

cat("\n")

# Validate quality_fundamentals.csv
if (file.exists(files$quality)) {
  df <- read.csv(files$quality, stringsAsFactors = FALSE)
  cat("--- quality_fundamentals.csv ---\n")
  cat("  Rows:", nrow(df), "\n")
  cat("  Columns:", ncol(df), "\n")

  required_cols <- c("symbol", "SALES_Y1", "PAT_Y1", "REV_CAGR_5Y", "PAT_CAGR_5Y",
                     "AVG_ROE_5Y", "AVG_ROCE_5Y", "CFO_Y1", "FCF_Y1")
  missing <- setdiff(required_cols, names(df))

  if (length(missing) == 0) {
    cat("  ✓ All required columns present\n")
  } else {
    cat("  ✗ Missing columns:", paste(missing, collapse = ", "), "\n")
    all_passed <- FALSE
  }

  # Check for non-NA values
  if (nrow(df) > 0) {
    sales_y1_valid <- sum(!is.na(df$SALES_Y1)) / nrow(df) * 100
    pat_cagr_valid <- sum(!is.na(df$PAT_CAGR_5Y)) / nrow(df) * 100

    cat(sprintf("  Data completeness: SALES_Y1=%.0f%%, PAT_CAGR_5Y=%.0f%%\n",
                sales_y1_valid, pat_cagr_valid))

    if (sales_y1_valid < 50) {
      cat("  ⚠ Warning: Low data completeness (<50%)\n")
    }
  }

  # Show sample
  cat("  Sample row:\n")
  if (nrow(df) > 0) {
    sample_cols <- intersect(c("symbol", "SALES_Y1", "PAT_Y1", "REV_CAGR_5Y", "AVG_ROE_5Y"), names(df))
    print(df[1, sample_cols])
  }
  cat("\n")
}

# Validate quarterly_eps.csv
if (file.exists(files$quarterly)) {
  df <- read.csv(files$quarterly, stringsAsFactors = FALSE)
  cat("--- quarterly_eps.csv ---\n")
  cat("  Rows:", nrow(df), "\n")
  cat("  Unique symbols:", length(unique(df$symbol)), "\n")

  required_cols <- c("symbol", "quarter_num", "revenue", "net_profit", "eps")
  missing <- setdiff(required_cols, names(df))

  if (length(missing) == 0) {
    cat("  ✓ All required columns present\n")
  } else {
    cat("  ✗ Missing columns:", paste(missing, collapse = ", "), "\n")
    all_passed <- FALSE
  }

  # Check quarters per symbol
  if (nrow(df) > 0) {
    qtrs_per_sym <- df %>% group_by(symbol) %>% summarise(n_qtrs = n())
    avg_qtrs <- mean(qtrs_per_sym$n_qtrs)
    cat(sprintf("  Avg quarters per symbol: %.1f (target: 8)\n", avg_qtrs))

    if (avg_qtrs < 4) {
      cat("  ⚠ Warning: Low quarter coverage (<4 per symbol)\n")
    }
  }

  # Show sample
  cat("  Sample rows (first symbol):\n")
  if (nrow(df) > 0) {
    first_sym <- df$symbol[1]
    sample <- df[df$symbol == first_sym, c("symbol", "quarter_num", "revenue", "eps")]
    print(head(sample, 3))
  }
  cat("\n")
}

# Validate peer_comparisons.csv
if (file.exists(files$peers)) {
  df <- read.csv(files$peers, stringsAsFactors = FALSE)
  cat("--- peer_comparisons.csv ---\n")
  cat("  Rows:", nrow(df), "\n")

  if ("Target_Symbol" %in% names(df)) {
    cat("  Target symbols:", length(unique(df$Target_Symbol)), "\n")
    cat("  ✓ Target_Symbol column present\n")
  } else {
    cat("  ✗ Missing Target_Symbol column\n")
    all_passed <- FALSE
  }

  # Show sample
  if (nrow(df) > 0) {
    cat("  Sample peer row:\n")
    sample_cols <- intersect(c("Target_Symbol", "Company", "CMP", "P.E", "Market.Cap"), names(df))
    if (length(sample_cols) > 0) {
      print(df[1, sample_cols])
    }
  }
  cat("\n")
}

# Validate cashflow_data.csv
if (file.exists(files$cashflow)) {
  df <- read.csv(files$cashflow, stringsAsFactors = FALSE)
  cat("--- cashflow_data.csv ---\n")
  cat("  Rows:", nrow(df), "\n")

  required_cols <- c("symbol", "CFO_Y1", "CAPEX_Y1", "FCF_Y1")
  missing <- setdiff(required_cols, names(df))

  if (length(missing) == 0) {
    cat("  ✓ All required columns present\n")
  } else {
    cat("  ✗ Missing columns:", paste(missing, collapse = ", "), "\n")
    all_passed <- FALSE
  }

  # Check for non-NA values
  if (nrow(df) > 0) {
    cfo_valid <- sum(!is.na(df$CFO_Y1)) / nrow(df) * 100
    cat(sprintf("  Data completeness: CFO_Y1=%.0f%%\n", cfo_valid))

    if (cfo_valid < 50) {
      cat("  ⚠ Warning: Low CFO data completeness (<50%)\n")
    }
  }

  # Show sample
  cat("  Sample row:\n")
  if (nrow(df) > 0) {
    sample_cols <- intersect(c("symbol", "CFO_Y1", "CAPEX_Y1", "FCF_Y1"), names(df))
    print(df[1, sample_cols])
  }
  cat("\n")
}

# Summary
cat("=== Validation Summary ===\n")
if (all_passed) {
  cat("✓ All validation checks PASSED\n")
  cat("\nBacklog items unblocked:\n")
  cat("  A4 - Earnings Acceleration Screener\n")
  cat("  A7 - Quality Compounder Screener\n")
  cat("  D1 - DuPont Decomposition Engine\n")
  cat("  D2 - Earnings Quality Score\n")
  cat("  D5 - Forensic Accounting Suite\n")
  cat("  D6 - Competitive Moat Score\n")
  cat("  E2 - Peer Comparison Engine\n")
  cat("\nNext step: Integrate into sector_rotation_report.py\n")
} else {
  cat("✗ Some validation checks FAILED\n")
  cat("Review errors above and re-run fetch script if needed.\n")
}
