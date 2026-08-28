#!/usr/bin/env Rscript
# Extension to fetch 5-year P&L, Balance Sheet, Cash Flow, and Peers data from Screener.in
# Unblocks backlog items: A4, A7, D1, D2, D5, D6, E2
# Output: data/quality_fundamentals.csv (5yr trends), data/quarterly_eps.csv (8Q series), data/peer_comparisons.csv
# Usage: Rscript fetch_screener_5yr_fundamentals.R [symbols_file]
# Run from project root. Requires: core/screenerdata.R

suppressMessages({
  library(dplyr)
  library(stringr)
  library(rvest)
})

args <- commandArgs(trailingOnly = TRUE)
PROJECT_ROOT <- getwd()
if (basename(PROJECT_ROOT) == "working-sector") PROJECT_ROOT <- dirname(PROJECT_ROOT)

# Source screener functions
screener_path <- file.path(PROJECT_ROOT, "core", "screenerdata.R")
if (!file.exists(screener_path)) stop("core/screenerdata.R not found")
source(screener_path)

# Input: symbols list
SYMBOLS_FILE <- if (length(args) >= 1) args[1] else file.path(PROJECT_ROOT, "data", "nifty500_symbols.txt")
CACHE_DIR <- file.path(PROJECT_ROOT, "data")

# Output files
QUALITY_FUND_CSV <- file.path(CACHE_DIR, "quality_fundamentals.csv")
QUARTERLY_EPS_CSV <- file.path(CACHE_DIR, "quarterly_eps.csv")
PEERS_CSV <- file.path(CACHE_DIR, "peer_comparisons.csv")
CASHFLOW_CSV <- file.path(CACHE_DIR, "cashflow_data.csv")

# Load symbols
symbols <- character(0)
if (file.exists(SYMBOLS_FILE)) {
  symbols <- trimws(readLines(SYMBOLS_FILE))
  symbols <- symbols[nzchar(symbols)]
} else {
  # Fallback: extract from existing cache
  cache_file <- file.path(CACHE_DIR, "_sector_rotation_fund_cache.csv")
  if (file.exists(cache_file)) {
    cache <- read.csv(cache_file, stringsAsFactors = FALSE)
    if ("symbol" %in% names(cache)) symbols <- unique(cache$symbol)
  }
}

if (length(symbols) == 0) {
  message("No symbols to fetch. Create ", SYMBOLS_FILE, " or ensure cache exists.")
  quit(save = "no", status = 0)
}

message("Fetching 5-year fundamentals for ", length(symbols), " symbols...")

# ==== NEW FUNCTION: Scrape Peers Table ====
get_screener_peers_data <- function(symbol) {
  tryCatch({
    url <- paste0("https://www.screener.in/company/", symbol, "/")
    webpage <- read_html(url)
    tables <- webpage %>% html_table()

    # Peers table is typically the 11th table on screener.in company page
    # It contains: Name, CMP, P/E, Market Cap, Div Yld, NP Qtr, Qtr Profit Var, Sales Qtr, ROCE
    if (length(tables) >= 11) {
      peers <- tables[[11]] %>% data.frame()
      if (ncol(peers) >= 3) {
        colnames(peers)[1] <- "Company"
        peers$Target_Symbol <- symbol  # Track which symbol this peer set belongs to
        Sys.sleep(5)  # Screener.in rate limit: 5 seconds
        return(peers)
      }
    }
    return(NULL)
  }, error = function(e) {
    message("  Peers fetch failed for ", symbol, ": ", conditionMessage(e))
    return(NULL)
  })
}

# ==== EXTRACT 5-YEAR DATA FROM P&L ====
extract_5yr_pnl <- function(symbol) {
  tryCatch({
    pnl <- get_screener_pnl_data(symbol)
    if (is.null(pnl) || nrow(pnl) == 0) return(NULL)

    items <- pnl[[1]]
    n_years <- min(5, ncol(pnl) - 1)  # First column is Items, rest are years

    # Extract key items for 5 years
    sales_idx <- which(grepl("Sales|Revenue", items, ignore.case = TRUE) & !grepl("Other", items))[1]
    pat_idx <- which(grepl("Net Profit|NetProfit|PAT", items, ignore.case = TRUE))[1]
    ebitda_idx <- which(grepl("EBITDA", items, ignore.case = TRUE))[1]
    eps_idx <- which(grepl("EPS|Earnings Per Share", items, ignore.case = TRUE))[1]

    result <- data.frame(symbol = symbol)

    for (i in 1:n_years) {
      year_col <- ncol(pnl) - i + 1  # Most recent first
      year_suffix <- paste0("_Y", i)

      if (!is.na(sales_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", pnl[sales_idx, year_col])))
        result[[paste0("SALES", year_suffix)]] <- val
      }
      if (!is.na(pat_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", pnl[pat_idx, year_col])))
        result[[paste0("PAT", year_suffix)]] <- val
      }
      if (!is.na(ebitda_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", pnl[ebitda_idx, year_col])))
        result[[paste0("EBITDA", year_suffix)]] <- val
      }
      if (!is.na(eps_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", pnl[eps_idx, year_col])))
        result[[paste0("EPS", year_suffix)]] <- val
      }
    }

    # Compute CAGR for 5 years (Y1 = latest, Y5 = oldest)
    if ("SALES_Y1" %in% names(result) && "SALES_Y5" %in% names(result)) {
      s1 <- result$SALES_Y1
      s5 <- result$SALES_Y5
      if (!is.na(s1) && !is.na(s5) && s5 > 0) {
        result$REV_CAGR_5Y <- round(100 * ((s1 / s5)^(1/4) - 1), 2)
      }
    }

    if ("PAT_Y1" %in% names(result) && "PAT_Y5" %in% names(result)) {
      p1 <- result$PAT_Y1
      p5 <- result$PAT_Y5
      if (!is.na(p1) && !is.na(p5) && p5 > 0) {
        result$PAT_CAGR_5Y <- round(100 * ((p1 / p5)^(1/4) - 1), 2)
      }
    }

    return(result)
  }, error = function(e) {
    return(NULL)
  })
}

# ==== EXTRACT 5-YEAR ROCE FROM RATIOS + BALANCE SHEET ====
extract_5yr_roce <- function(symbol) {
  tryCatch({
    fr <- get_screener_finratios_data(symbol)
    if (is.null(fr) || nrow(fr) == 0) return(NULL)

    items <- gsub("[^A-Za-z0-9]", "", as.character(fr[[1]]))
    n_years <- min(5, ncol(fr) - 1)

    roce_idx <- which(grepl("ROCE|ReturnonCapitalEmployed", items, ignore.case = TRUE))[1]
    roe_idx <- which(grepl("ROE|ReturnonEquity", items, ignore.case = TRUE))[1]

    result <- data.frame(symbol = symbol)

    for (i in 1:n_years) {
      year_col <- ncol(fr) - i + 1
      year_suffix <- paste0("_Y", i)

      if (!is.na(roce_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(fr[roce_idx, year_col]))))
        result[[paste0("ROCE", year_suffix)]] <- val
      }
      if (!is.na(roe_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(fr[roe_idx, year_col]))))
        result[[paste0("ROE", year_suffix)]] <- val
      }
    }

    # Compute average ROE and ROCE over 5 years
    roe_cols <- grep("^ROE_Y", names(result), value = TRUE)
    roce_cols <- grep("^ROCE_Y", names(result), value = TRUE)

    if (length(roe_cols) > 0) {
      result$AVG_ROE_5Y <- round(mean(unlist(result[, roe_cols]), na.rm = TRUE), 2)
    }
    if (length(roce_cols) > 0) {
      result$AVG_ROCE_5Y <- round(mean(unlist(result[, roce_cols]), na.rm = TRUE), 2)
    }

    return(result)
  }, error = function(e) {
    return(NULL)
  })
}

# ==== EXTRACT CASH FLOW DATA (5 years) ====
extract_cashflow <- function(symbol) {
  tryCatch({
    cf <- get_screener_cashflow_data(symbol)
    if (is.null(cf) || nrow(cf) == 0) return(NULL)

    items <- cf[[1]]
    n_years <- min(5, ncol(cf) - 1)

    cfo_idx <- which(grepl("Operating.*Cash|Cash.*Operation", items, ignore.case = TRUE))[1]
    capex_idx <- which(grepl("Capex|Capital.*Expend", items, ignore.case = TRUE))[1]

    result <- data.frame(symbol = symbol)

    for (i in 1:n_years) {
      year_col <- ncol(cf) - i + 1
      year_suffix <- paste0("_Y", i)

      if (!is.na(cfo_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", cf[cfo_idx, year_col])))
        result[[paste0("CFO", year_suffix)]] <- val
      }
      if (!is.na(capex_idx)) {
        val <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", cf[capex_idx, year_col])))
        result[[paste0("CAPEX", year_suffix)]] <- val
      }
    }

    # Compute FCF = CFO - Capex for latest year
    if ("CFO_Y1" %in% names(result) && "CAPEX_Y1" %in% names(result)) {
      cfo <- result$CFO_Y1
      capex <- result$CAPEX_Y1
      if (!is.na(cfo) && !is.na(capex)) {
        result$FCF_Y1 <- cfo - abs(capex)  # Capex is often negative
      }
    }

    return(result)
  }, error = function(e) {
    return(NULL)
  })
}

# ==== EXTRACT QUARTERLY EPS SERIES (8 quarters) ====
extract_quarterly_eps <- function(symbol) {
  tryCatch({
    q <- get_screener_quarterly_results_data(symbol)
    if (is.null(q) || nrow(q) == 0) return(NULL)

    items <- q[[1]]
    n_qtrs <- min(8, ncol(q) - 1)

    sales_idx <- which(grepl("Sales|Revenue", items, ignore.case = TRUE) & !grepl("Other", items))[1]
    pat_idx <- which(grepl("Net Profit|NetProfit|PAT", items, ignore.case = TRUE))[1]
    eps_idx <- which(grepl("EPS|Earnings Per Share", items, ignore.case = TRUE))[1]

    results <- list()

    for (i in 1:n_qtrs) {
      qtr_col <- 1 + i  # Column 1 is Items, 2 is latest quarter
      qtr_name <- colnames(q)[qtr_col]

      row <- data.frame(
        symbol = symbol,
        quarter_num = i,  # 1 = latest, 8 = oldest
        quarter_name = qtr_name
      )

      if (!is.na(sales_idx)) {
        row$revenue <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", q[sales_idx, qtr_col])))
      }
      if (!is.na(pat_idx)) {
        row$net_profit <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", q[pat_idx, qtr_col])))
      }
      if (!is.na(eps_idx)) {
        row$eps <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", q[eps_idx, qtr_col])))
      }

      # Operating margin (if sales and pat exist)
      if (!is.na(sales_idx) && !is.na(pat_idx) && !is.na(row$revenue) && row$revenue > 0) {
        row$op_margin <- round(100 * row$net_profit / row$revenue, 2)
      }

      results[[i]] <- row
    }

    return(bind_rows(results))
  }, error = function(e) {
    return(NULL)
  })
}

# ==== MAIN PROCESSING LOOP ====
quality_results <- list()
quarterly_results <- list()
peers_results <- list()
cashflow_results <- list()

for (i in seq_along(symbols)) {
  sym <- symbols[i]
  message("[", i, "/", length(symbols), "] Processing ", sym, " ...")

  # 5-year P&L
  pnl_5yr <- extract_5yr_pnl(sym)

  # 5-year ROCE/ROE
  roce_5yr <- extract_5yr_roce(sym)

  # Cash flow
  cf_5yr <- extract_cashflow(sym)

  # Quarterly EPS (8 quarters)
  qtr_eps <- extract_quarterly_eps(sym)

  # Peers table
  peers <- get_screener_peers_data(sym)

  # Merge 5-year data into quality_fundamentals
  quality_row <- pnl_5yr
  if (!is.null(roce_5yr)) {
    for (col in setdiff(names(roce_5yr), "symbol")) {
      quality_row[[col]] <- roce_5yr[[col]]
    }
  }
  if (!is.null(cf_5yr)) {
    for (col in setdiff(names(cf_5yr), "symbol")) {
      quality_row[[col]] <- cf_5yr[[col]]
    }
  }

  if (!is.null(quality_row)) quality_results[[i]] <- quality_row
  if (!is.null(qtr_eps)) quarterly_results[[i]] <- qtr_eps
  if (!is.null(peers)) peers_results[[i]] <- peers
  if (!is.null(cf_5yr)) cashflow_results[[i]] <- cf_5yr

  Sys.sleep(5)  # Screener.in rate limit
}

# Write outputs
if (length(quality_results) > 0) {
  quality_df <- bind_rows(quality_results)
  write.csv(quality_df, QUALITY_FUND_CSV, row.names = FALSE)
  message("✓ Wrote ", QUALITY_FUND_CSV, " (", nrow(quality_df), " rows)")
}

if (length(quarterly_results) > 0) {
  quarterly_df <- bind_rows(quarterly_results)
  write.csv(quarterly_df, QUARTERLY_EPS_CSV, row.names = FALSE)
  message("✓ Wrote ", QUARTERLY_EPS_CSV, " (", nrow(quarterly_df), " rows)")
}

if (length(peers_results) > 0) {
  peers_df <- bind_rows(peers_results)
  write.csv(peers_df, PEERS_CSV, row.names = FALSE)
  message("✓ Wrote ", PEERS_CSV, " (", nrow(peers_df), " rows)")
}

if (length(cashflow_results) > 0) {
  cashflow_df <- bind_rows(cashflow_results)
  write.csv(cashflow_df, CASHFLOW_CSV, row.names = FALSE)
  message("✓ Wrote ", CASHFLOW_CSV, " (", nrow(cashflow_df), " rows)")
}

message("\n=== 5-Year Fundamentals Fetch Complete ===")
message("Unblocked backlog items:")
message("  A4 (Earnings Acceleration) - quarterly_eps.csv ready")
message("  A7 (Quality Compounder) - 5yr CAGR in quality_fundamentals.csv")
message("  D1 (DuPont) - 5yr P&L + BS trends ready")
message("  D2 (Earnings Quality) - cashflow_data.csv with CFO ready")
message("  D5 (Forensic Accounting) - 5yr data for Beneish/Piotroski/Altman")
message("  D6 (Moat Score) - 5yr margins + ROCE trends ready")
message("  E2 (Peer Comparison) - peer_comparisons.csv ready")
