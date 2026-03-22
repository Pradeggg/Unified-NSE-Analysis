#!/usr/bin/env Rscript
# Fetch P&L, Quarterly Results, Balance Sheet, and Financial Ratios from Screener.in for a symbol list.
# Writes working-sector/output/fundamental_details.csv (symbol, pnl_summary, quarterly_summary, balance_sheet_summary, ratios_summary).
# Ratios: from screener financial ratios table when available; when not (e.g. ROCE, ROE, EPS missing),
# they are computed from P&L and Balance sheet (ROE = Net Profit/Equity; ROCE = EBIT or EBITDA/Capital Employed; EPS from P&L; NPM = Net Profit/Sales).
# Usage: Rscript fetch_screener_fundamental_details.R [symbols_file] [output_csv]
# If NSE_SECTOR is set (e.g. plastics_and_packaging), uses working-sector/<sector>_universe.csv and output/<sector>/fundamental_details.csv.
# Run from project root. Requires: core/screenerdata.R (get_screener_pnl_data, get_screener_quarterly_results_data, get_screener_balancesheet_data, get_screener_finratios_data).

suppressMessages({
  library(dplyr)
  library(stringr)
})

args <- commandArgs(trailingOnly = TRUE)
PROJECT_ROOT <- getwd()
if (basename(PROJECT_ROOT) == "working-sector") PROJECT_ROOT <- dirname(PROJECT_ROOT)
WORKING_SECTOR <- file.path(PROJECT_ROOT, "working-sector")
NSE_SECTOR <- Sys.getenv("NSE_SECTOR", "auto_components")
NSE_SECTOR <- tolower(trimws(gsub("[ -]", "_", NSE_SECTOR)))
OUTPUT_DIR <- file.path(WORKING_SECTOR, "output", NSE_SECTOR)
if (!dir.exists(OUTPUT_DIR)) OUTPUT_DIR <- file.path(WORKING_SECTOR, "output")
SYMBOLS_FILE <- if (length(args) >= 1) args[1] else file.path(OUTPUT_DIR, "symbols_to_fetch.txt")
UNIVERSE_CSV <- file.path(WORKING_SECTOR, paste0(NSE_SECTOR, "_universe.csv"))
if (!file.exists(UNIVERSE_CSV)) UNIVERSE_CSV <- file.path(WORKING_SECTOR, "auto_components_universe.csv")
OUT_CSV <- if (length(args) >= 2) args[2] else file.path(OUTPUT_DIR, "fundamental_details.csv")

screener_path <- file.path(PROJECT_ROOT, "core", "screenerdata.R")
if (!file.exists(screener_path)) stop("core/screenerdata.R not found")
source(screener_path)

symbols <- character(0)
if (file.exists(SYMBOLS_FILE)) {
  symbols <- trimws(readLines(SYMBOLS_FILE))
  symbols <- symbols[nzchar(symbols)]
}
if (length(symbols) == 0 && file.exists(UNIVERSE_CSV)) {
  u <- read.csv(UNIVERSE_CSV, stringsAsFactors = FALSE)
  if ("SYMBOL" %in% names(u)) symbols <- trimws(as.character(u$SYMBOL))
}
if (length(symbols) == 0 && !file.exists(SYMBOLS_FILE)) {
  message("Symbols file not found: ", SYMBOLS_FILE, " and no universe CSV at ", UNIVERSE_CSV)
  quit(save = "no", status = 0)
}
if (length(symbols) == 0) {
  message("No symbols to fetch.")
  quit(save = "no", status = 0)
}

# P&L: extract Sales, EBITDA, Net Profit (or PAT), EPS for latest 2 years and YoY change
format_pnl <- function(pnl) {
  if (is.null(pnl) || nrow(pnl) == 0 || ncol(pnl) < 2) return(NA_character_)
  items <- pnl[[1]]
  vals <- as.data.frame(lapply(pnl[, -1, drop = FALSE], function(x) suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", x)))))
  if (ncol(vals) < 2) return(NA_character_)
  y1 <- vals[[ncol(vals)]]
  y0 <- vals[[ncol(vals) - 1]]
  out <- character(0)
  for (label in c("Sales", "Revenue", "NetProfit", "Net Profit", "PAT", "EBITDA")) {
    i <- which(grepl(label, items, ignore.case = TRUE) & !grepl("Growth|%", items, ignore.case = TRUE))[1]
    if (is.na(i)) next
    v1 <- y1[i]; v0 <- y0[i]
    if (is.na(v1)) next
    yoy <- if (!is.na(v0) && v0 != 0) round(100 * (v1 - v0) / abs(v0), 1) else NA
    lab <- gsub("Net Profit|PAT", "Net Profit", label)
    if (is.na(yoy)) out <- c(out, paste0(lab, ": ", round(v1, 0), " Cr"))
    else out <- c(out, paste0(lab, ": ", round(v1, 0), " Cr (YoY ", if (yoy >= 0) "+" else "", yoy, "%)"))
  }
  # EPS from P&L if present (Earnings Per Share)
  i_eps <- which(grepl("EarningsPerShare|EPS|Earnings Per Share", items, ignore.case = TRUE) & !grepl("Diluted|Growth", items, ignore.case = TRUE))[1]
  if (!is.na(i_eps)) {
    v_eps <- y1[i_eps]
    if (!is.na(v_eps)) out <- c(out, paste0("EPS: ", round(v_eps, 2)))
  }
  if (length(out) == 0) return(NA_character_)
  paste(out, collapse = "; ")
}

# Quarterly: last 4 quarters for Sales and Net Profit
format_quarterly <- function(q) {
  if (is.null(q) || nrow(q) == 0 || ncol(q) < 3) return(NA_character_)
  items <- q[[1]]
  nq <- min(4, ncol(q) - 1)
  cols <- seq(to = ncol(q), length.out = nq)
  out <- character(0)
  for (label in c("Sales", "Revenue", "NetProfit", "Net Profit", "PAT")) {
    i <- which(grepl(label, items, ignore.case = TRUE) & !grepl("Other", items, ignore.case = TRUE))[1]
    if (is.na(i)) next
    v <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(q[i, cols]))))
    if (all(is.na(v))) next
    v <- round(v, 0)
    lab <- if (grepl("Net|PAT", label, ignore.case = TRUE)) "Net Profit" else "Sales"
    out <- c(out, paste0(lab, " last ", nq, "Q: ", paste(v, collapse = ", "), " Cr"))
  }
  if (length(out) == 0) return(NA_character_)
  paste(out, collapse = "; ")
}

# Balance sheet: Shareholders Funds, Total Debt, Cash (latest); optional Debt/Equity
format_bs <- function(bs) {
  if (is.null(bs) || nrow(bs) == 0 || ncol(bs) < 2) return(NA_character_)
  items <- bs[[1]]
  latest <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(bs[[ncol(bs)]]))))
  out <- character(0)
  equity_val <- debt_val <- NA_real_
  for (label in c("Shareholders Funds", "Equity Share Capital", "Total Debt", "Borrowings", "Cash", "Cash And")) {
    i <- which(grepl(gsub(" ", ".*", label), items, ignore.case = TRUE))[1]
    if (is.na(i)) next
    v <- latest[i]
    if (is.na(v)) next
    lab <- if (grepl("Shareholders|Equity", label)) "Equity" else if (grepl("Debt|Borrow", label)) "Debt" else "Cash"
    if (lab == "Equity") equity_val <- v
    if (lab == "Debt") debt_val <- v
    if (lab %in% sub(":.*", "", out)) next
    out <- c(out, paste0(lab, ": ", round(v, 0), " Cr"))
  }
  if (!is.na(debt_val) && !is.na(equity_val) && equity_val > 0) {
    de_ratio <- round(debt_val / equity_val, 2)
    out <- c(out, paste0("Debt/Equity: ", de_ratio))
  }
  if (length(out) == 0) return(NA_character_)
  paste(out, collapse = "; ")
}

# Helper: get latest (most recent column) numeric value from P&L for a row matching pattern
get_pnl_latest <- function(pnl, pattern) {
  if (is.null(pnl) || nrow(pnl) == 0 || ncol(pnl) < 2) return(NA_real_)
  items <- pnl[[1]]
  i <- which(grepl(pattern, items, ignore.case = TRUE))[1]
  if (is.na(i)) return(NA_real_)
  v <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(pnl[i, ncol(pnl)]))))
  if (is.na(v)) return(NA_real_)
  v
}

# Helper: get latest numeric value from Balance sheet for a row matching pattern
get_bs_latest <- function(bs, pattern) {
  if (is.null(bs) || nrow(bs) == 0 || ncol(bs) < 2) return(NA_real_)
  items <- bs[[1]]
  i <- which(grepl(pattern, items, ignore.case = TRUE))[1]
  if (is.na(i)) return(NA_real_)
  v <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(bs[i, ncol(bs)]))))
  if (is.na(v)) return(NA_real_)
  v
}

# Compute ROCE, ROE, EPS (and optionally NPM) from P&L and Balance sheet when not in finratios
computed_ratios_from_pnl_bs <- function(pnl, bs) {
  out <- character(0)
  if (is.null(pnl) && is.null(bs)) return(out)
  net_profit <- get_pnl_latest(pnl, "NetProfit|Net Profit|PAT")
  equity     <- get_bs_latest(bs, "Shareholders Funds|Equity Share Capital")
  debt       <- get_bs_latest(bs, "Total Debt|Borrowings")
  ebitda     <- get_pnl_latest(pnl, "EBITDA")
  sales      <- get_pnl_latest(pnl, "Sales|Revenue")
  eps        <- get_pnl_latest(pnl, "EarningsPerShare|EPS|Earnings Per Share")
  # ROE = 100 * Net Profit / Shareholders' Equity
  if (!is.na(net_profit) && !is.na(equity) && equity > 0) {
    roe <- round(100 * net_profit / equity, 2)
    out <- c(out, paste0("ROE: ", roe, "%"))
  }
  # ROCE = 100 * EBIT or EBITDA / (Equity + Debt). Prefer Operating Profit / PBIT when available.
  ebit <- get_pnl_latest(pnl, "Operating Profit|PBIT|Profit Before Interest|EBIT")
  if (is.na(ebit)) ebit <- ebitda
  cap_employed <- NA_real_
  if (!is.na(equity)) cap_employed <- equity
  if (!is.na(debt))  cap_employed <- if (is.na(cap_employed)) debt else cap_employed + debt
  if (!is.na(ebit) && !is.na(cap_employed) && cap_employed > 0) {
    roce <- round(100 * ebit / cap_employed, 2)
    out <- c(out, paste0("ROCE: ", roce, "%"))
  }
  # EPS from P&L (often in Rs)
  if (!is.na(eps) && is.finite(eps)) {
    out <- c(out, paste0("EPS: ", round(eps, 2)))
  }
  # NPM = 100 * Net Profit / Sales
  if (!is.na(net_profit) && !is.na(sales) && sales > 0) {
    npm <- round(100 * net_profit / sales, 2)
    out <- c(out, paste0("NPM: ", npm, "%"))
  }
  out
}

# Financial ratios: ROCE, ROE, EPS, PE, PB, etc. (from get_screener_finratios_data; fill missing from P&L/BS)
format_ratios <- function(fr, pnl = NULL, bs = NULL) {
  out <- character(0)
  # First: from finratios table (company page)
  if (!is.null(fr) && nrow(fr) > 0 && ncol(fr) >= 2) {
    items <- gsub("[^A-Za-z0-9]", "", as.character(fr[[1]]))
    last_col <- ncol(fr)
    vals <- suppressWarnings(as.numeric(gsub("[^0-9.\\-]", "", as.character(fr[[last_col]]))))
    ratio_specs <- list(
      list(pat = "ROCE|ReturnonCapitalEmployed", lab = "ROCE", suf = "%"),
      list(pat = "ROE|ReturnonEquity", lab = "ROE", suf = "%"),
      list(pat = "EPS|EarningsPerShare", lab = "EPS", suf = ""),
      list(pat = "PE|PricetoEarning", lab = "PE", suf = ""),
      list(pat = "PB|PricetoBook", lab = "PB", suf = ""),
      list(pat = "DebttoEquity|Debttoequity", lab = "D/E", suf = ""),
      list(pat = "InterestCoverage", lab = "Interest Cov", suf = "x"),
      list(pat = "OperatingProfitMargin|OPM", lab = "OPM", suf = "%"),
      list(pat = "NetProfitMargin|NPM", lab = "NPM", suf = "%"),
      list(pat = "DividendYield", lab = "Div Yield", suf = "%")
    )
    for (spec in ratio_specs) {
      i <- which(grepl(spec$pat, items, ignore.case = TRUE))[1]
      if (is.na(i)) next
      v <- vals[i]
      if (is.na(v)) next
      suf <- spec$suf
      out <- c(out, paste0(spec$lab, ": ", round(v, 2), suf))
    }
  }
  # Second: fill ROCE, ROE, EPS, NPM from P&L/BS when missing from screener ratios
  have_label <- function(lab) any(grepl(paste0("^", lab, ":"), out))
  computed <- computed_ratios_from_pnl_bs(pnl, bs)
  for (s in computed) {
    lab <- sub(":.*", "", s)
    if (!have_label(lab)) out <- c(out, s)
  }
  if (length(out) == 0) return(NA_character_)
  paste(out, collapse = "; ")
}

results <- list()
for (i in seq_along(symbols)) {
  sym <- symbols[i]
  message("[", i, "/", length(symbols), "] ", sym, " ...")
  pnl_sum <- quarterly_sum <- bs_sum <- ratios_sum <- NA_character_
  pnl <- NULL
  bs  <- NULL
  tryCatch({
    pnl <- get_screener_pnl_data(sym)
    pnl_sum <- format_pnl(pnl)
    Sys.sleep(2)
  }, error = function(e) NULL)
  tryCatch({
    q <- get_screener_quarterly_results_data(sym)
    quarterly_sum <- format_quarterly(q)
    Sys.sleep(2)
  }, error = function(e) NULL)
  tryCatch({
    bs <- get_screener_balancesheet_data(sym)
    bs_sum <- format_bs(bs)
    Sys.sleep(2)
  }, error = function(e) NULL)
  tryCatch({
    fr <- get_screener_finratios_data(sym)
    ratios_sum <- format_ratios(fr, pnl = pnl, bs = bs)
    Sys.sleep(2)
  }, error = function(e) NULL)
  results[[i]] <- data.frame(
    symbol = sym,
    pnl_summary = if (is.na(pnl_sum)) "" else pnl_sum,
    quarterly_summary = if (is.na(quarterly_sum)) "" else quarterly_sum,
    balance_sheet_summary = if (is.na(bs_sum)) "" else bs_sum,
    ratios_summary = if (is.na(ratios_sum)) "" else ratios_sum,
    stringsAsFactors = FALSE
  )
}

out_df <- bind_rows(results)
dir.create(dirname(OUT_CSV), recursive = TRUE, showWarnings = FALSE)
write.csv(out_df, OUT_CSV, row.names = FALSE)
message("Wrote ", OUT_CSV)
