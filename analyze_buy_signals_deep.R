#!/usr/bin/env Rscript
# Deep-dive on STRONG_BUY + BUY names from latest comprehensive_nse_enhanced CSV

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(commonmark)
})

md_pipe_table <- function(df) {
  if (nrow(df) == 0) return("(no rows)\n")
  nm <- names(df)
  header <- paste0("| ", paste(nm, collapse = " | "), " |")
  sep <- paste0("|", paste(rep("---", length(nm)), collapse = "|"), "|")
  rows <- apply(df, 1L, function(row) paste0("| ", paste(as.character(row), collapse = " | "), " |"))
  paste(paste(c(header, sep, rows), collapse = "\n"), "\n")
}

write_buy_deep_html <- function(out_html, ad, latest_file, html_fragment,
                                n_total, n_buys, n_sb, n_buy, gen_time = Sys.time()) {
  pct <- sprintf("%.1f", 100 * n_buys / max(1L, n_total))
  analysis_pretty <- format(ad, "%B %d, %Y")
  src <- basename(latest_file)
  html_doc <- paste0(
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n',
    '<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
    '<title>BUY Deep Analysis — ', format(ad, "%Y-%m-%d"), '</title>\n',
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n',
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n',
    '<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n',
    '<style>\n',
    '        * {\n            margin: 0;\n            padding: 0;\n            box-sizing: border-box;\n        }\n',
    '        body {\n            font-family: "Roboto", "Google Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;\n',
    '            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);\n',
    '            min-height: 100vh;\n            color: #212121;\n            font-weight: 400;\n            line-height: 1.6;\n        }\n',
    '        .container {\n            max-width: 100%;\n            margin: 0 auto;\n            padding: 20px;\n            width: 100%;\n        }\n',
    '        .header {\n            text-align: center;\n            margin-bottom: 30px;\n            color: white;\n        }\n',
    '        .header h1 {\n            font-size: 3rem;\n            font-weight: 300;\n            margin-bottom: 16px;\n            text-shadow: 0 2px 4px rgba(0,0,0,0.1);\n            letter-spacing: -0.5px;\n        }\n',
    '        .header p {\n            font-size: 1.25rem;\n            font-weight: 400;\n            opacity: 0.9;\n        }\n',
    '        .header .sub {\n            margin-top: 10px;\n            font-size: 1rem;\n            opacity: 0.8;\n        }\n',
    '        .header code {\n            background: rgba(255,255,255,0.18);\n            padding: 2px 10px;\n            border-radius: 6px;\n            font-size: 0.88em;\n        }\n',
    '        .summary-grid {\n            display: grid;\n            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));\n            gap: 1rem;\n            margin-bottom: 2rem;\n        }\n',
    '        .summary-card {\n            background: white;\n            border-radius: 8px;\n            padding: 1rem;\n            box-shadow: 0 2px 8px rgba(0,0,0,0.1);\n            text-align: center;\n        }\n',
    '        .summary-card .number {\n            font-size: 2rem;\n            font-weight: 300;\n            color: #764ba2;\n            margin: 0.5rem 0;\n        }\n',
    '        .summary-card p {\n            color: #7f8c8d;\n            font-size: 0.9rem;\n        }\n',
    '        .sector-section {\n            margin: 2rem 0;\n            padding: 2rem;\n            background: #f8f9fa;\n            border-radius: 12px;\n        }\n',
    '        .buy-deep-html {\n            font-size: 0.95rem;\n            color: #37474f;\n        }\n',
    '        .buy-deep-html h2 {\n            font-size: 2rem;\n            font-weight: 400;\n            color: #2c3e50;\n            margin-top: 2rem;\n            margin-bottom: 1rem;\n        }\n',
    '        .buy-deep-html h2:first-child { margin-top: 0; }\n',
    '        .buy-deep-html ul { margin: 1rem 0 1rem 1.25rem; }\n',
    '        .buy-deep-html li { margin: 0.35rem 0; }\n',
    '        .buy-deep-html li p { margin: 0.25rem 0; }\n',
    '        .buy-deep-html table {\n            background: white;\n            border-collapse: collapse;\n            width: 100%;\n            margin: 1.25rem 0;\n            font-size: 0.88rem;\n            border-radius: 8px;\n            overflow: hidden;\n            box-shadow: 0 2px 8px rgba(0,0,0,0.1);\n        }\n',
    '        .buy-deep-html th, .buy-deep-html td {\n            border: 1px solid #ecf0f1;\n            padding: 0.65rem 0.85rem;\n            text-align: left;\n            vertical-align: top;\n        }\n',
    '        .buy-deep-html thead th {\n            background: white;\n            color: #2c3e50;\n            font-weight: 600;\n        }\n',
    '        .buy-deep-html tbody tr:nth-child(even) { background: #fafbfc; }\n',
    '        .buy-deep-html hr {\n            border: none;\n            border-top: 1px solid #ecf0f1;\n            margin: 2rem 0;\n        }\n',
    '        .buy-deep-html strong { color: #2c3e50; }\n',
    '        .buy-deep-html em { color: #546e7a; }\n',
    '        @media (max-width: 768px) {\n            .summary-grid { grid-template-columns: 1fr; }\n            .header h1 { font-size: 2rem; }\n        }\n',
    '</style>\n</head>\n<body>\n',
    '    <div class="container">\n',
    '        <div class="header">\n',
    '            <h1>📊 BUY universe deep analysis</h1>\n',
    '            <p>STRONG_BUY + BUY cohort — technical, RS, CAN SLIM / Minervini &amp; fundamentals</p>\n',
    '            <p class="sub">Analysis Date: ', analysis_pretty, '</p>\n',
    '            <p class="sub">Source <code>', src, '</code> · Generated ',
    format(gen_time, "%Y-%m-%d %H:%M"), '</p>\n',
    '        </div>\n',
    '        <div class="summary-grid">\n',
    '            <div class="summary-card"><div class="number">', n_total, '</div><p>Filtered universe</p></div>\n',
    '            <div class="summary-card"><div class="number">', n_buys, '</div><p>STRONG_BUY + BUY (', pct, '%)</p></div>\n',
    '            <div class="summary-card"><div class="number">', n_sb, '</div><p>STRONG_BUY</p></div>\n',
    '            <div class="summary-card"><div class="number">', n_buy, '</div><p>BUY</p></div>\n',
    '        </div>\n',
    '        <div class="sector-section">\n',
    '            <div class="buy-deep-html">\n',
    html_fragment,
    '\n            </div>\n        </div>\n    </div>\n</body>\n</html>'
  )
  writeLines(html_doc, out_html)
}

project_root <- "/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/Unified-NSE-Analysis"
setwd(project_root)

analysis_files <- list.files("reports", pattern = "comprehensive_nse_enhanced_.*\\.csv$", full.names = TRUE)
if (length(analysis_files) == 0) stop("No comprehensive_nse_enhanced_*.csv in reports/")
latest_file <- analysis_files[order(file.info(analysis_files)$mtime, decreasing = TRUE)][1]

d <- read_csv(latest_file, show_col_types = FALSE)
ad <- suppressWarnings(as.Date(d$ANALYSIS_DATE[1]))
if (length(ad) == 0 || is.na(ad)) ad <- Sys.Date()
suffix <- format(ad, "%Y%m%d")

buys <- d %>%
  filter(TRADING_SIGNAL %in% c("STRONG_BUY", "BUY")) %>%
  arrange(desc(TECHNICAL_SCORE))

n_total <- nrow(d)
n_buys <- nrow(buys)
n_sb <- sum(buys$TRADING_SIGNAL == "STRONG_BUY", na.rm = TRUE)
n_buy <- sum(buys$TRADING_SIGNAL == "BUY", na.rm = TRUE)

fmt_vec <- function(x) paste(sprintf("%.1f", x), collapse = ", ")
qvec <- function(x) {
  x <- x[is.finite(x)]
  if (length(x) == 0) return("N/A")
  qs <- quantile(x, probs = c(0.1, 0.25, 0.5, 0.75, 0.9), na.rm = TRUE)
  sprintf("p10=%.1f, p25=%.1f, med=%.1f, p75=%.1f, p90=%.1f", qs[1], qs[2], qs[3], qs[4], qs[5])
}

md <- c()
md <- c(md, sprintf("# BUY universe deep analysis\n"))
md <- c(md, sprintf("**Source:** `%s`  \n", basename(latest_file)))
md <- c(md, sprintf("**Stock data date:** %s  \n", format(ad, "%Y-%m-%d")))
md <- c(md, sprintf("**Generated:** %s UTC (local)\n\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S")))
md <- c(md, sprintf("Universe: **%d** stocks with price/volume filters; **%d** STRONG_BUY + BUY (**%.1f%%**).\n\n",
                    n_total, n_buys, 100 * n_buys / max(1, n_total)))
md <- c(md, sprintf("- STRONG_BUY: **%d** | BUY: **%d**\n\n", n_sb, n_buy))

if (n_buys == 0) {
  md <- c(md, "No BUY / STRONG_BUY rows in this file.\n")
  out <- file.path("reports", sprintf("BUY_Deep_Analysis_%s.md", suffix))
  writeLines(md, out)
  idx_h2 <- which(grepl("^## ", md))[1]
  md_body <- if (!is.na(idx_h2)) md[idx_h2:length(md)] else paste("## Result\n\n", paste(md, collapse = ""), sep = "")
  frag <- commonmark::markdown_html(paste(md_body, collapse = "\n"), extensions = TRUE)
  out_html <- file.path("reports", sprintf("BUY_Deep_Analysis_%s.html", suffix))
  write_buy_deep_html(out_html, ad, latest_file, frag, n_total, n_buys, n_sb, n_buy)
  cat("Wrote:", out, "\nHTML:", out_html, "\n", sep = "")
  quit(save = "no")
}

# --- Technical layer ---
md <- c(md, "## Technical score & momentum\n\n")
md <- c(md, sprintf("- TECHNICAL_SCORE — %s\n", qvec(buys$TECHNICAL_SCORE)))
md <- c(md, sprintf("- RSI — mean **%.1f**; %% with RSI>70 (overbought): **%.1f%%**; RSI<40: **%.1f%%**\n",
                    mean(buys$RSI, na.rm = TRUE),
                    100 * mean(buys$RSI > 70, na.rm = TRUE),
                    100 * mean(buys$RSI < 40, na.rm = TRUE)))
md <- c(md, sprintf("- Price changes (%%): 1D mean **%.2f** | 1W **%.2f** | 1M **%.2f**\n",
                    mean(buys$CHANGE_1D, na.rm = TRUE),
                    mean(buys$CHANGE_1W, na.rm = TRUE),
                    mean(buys$CHANGE_1M, na.rm = TRUE)))

neg_m <- buys$CHANGE_1M < 0 & is.finite(buys$CHANGE_1M)
md <- c(md, sprintf("- Still flagged BUY with **negative 1M** return: **%d** names (check trend / pullback plays).\n\n", sum(neg_m)))

# --- Relative strength ---
md <- c(md, "## Relative strength vs NIFTY500 (50d)\n\n")
md <- c(md, sprintf("- RELATIVE_STRENGTH (%%) — %s\n", qvec(buys$RELATIVE_STRENGTH)))
md <- c(md, sprintf("- Mean RS: **%.2f%%**\n\n", mean(buys$RELATIVE_STRENGTH, na.rm = TRUE)))

# --- CAN SLIM / Minervini ---
md <- c(md, "## CAN SLIM & Minervini (within BUY list)\n\n")
md <- c(md, sprintf("- CAN_SLIM_SCORE — %s (max 20)\n", qvec(buys$CAN_SLIM_SCORE)))
md <- c(md, sprintf("- MINERVINI_SCORE — %s (max 20)\n", qvec(buys$MINERVINI_SCORE)))
dual <- buys$CAN_SLIM_SCORE >= 15 & buys$MINERVINI_SCORE >= 12 & !is.na(buys$CAN_SLIM_SCORE) & !is.na(buys$MINERVINI_SCORE)
md <- c(md, sprintf("- **Dual strength** (CAN SLIM ≥15 & Minervini ≥12): **%d** stocks\n\n", sum(dual)))

# --- Fundamentals ---
md <- c(md, "## Fundamental overlay (ENHANCED_FUND_SCORE)\n\n")
ef <- buys$ENHANCED_FUND_SCORE
ef <- ef[is.finite(ef)]
if (length(ef)) {
  md <- c(md, sprintf("- Distribution — %s\n", qvec(buys$ENHANCED_FUND_SCORE)))
  hi_f <- buys %>% filter(is.finite(ENHANCED_FUND_SCORE)) %>% arrange(desc(ENHANCED_FUND_SCORE)) %>% head(10)
  lo_f <- buys %>% filter(is.finite(ENHANCED_FUND_SCORE)) %>% arrange(ENHANCED_FUND_SCORE) %>% head(10)
  md <- c(md, "\n**Top 10 BUY names by enhanced fund score**\n\n| Rank | Symbol | Tech | Fund | Signal |\n|------|--------|------|------|--------|\n")
  for (i in seq_len(min(10, nrow(hi_f)))) {
    r <- hi_f[i, ]
    md <- c(md, sprintf("| %d | **%s** | %.1f | %.1f | %s |\n", i, r$SYMBOL, r$TECHNICAL_SCORE, r$ENHANCED_FUND_SCORE, r$TRADING_SIGNAL))
  }
  md <- c(md, "\n**Lowest fund scores among BUYs** (technical entry, weaker fundamentals — due diligence)\n\n| Symbol | Tech | Fund | RSI |\n|--------|------|------|-----|\n")
  for (i in seq_len(min(10, nrow(lo_f)))) {
    r <- lo_f[i, ]
    md <- c(md, sprintf("| **%s** | %.1f | %.1f | %.1f |\n", r$SYMBOL, r$TECHNICAL_SCORE, r$ENHANCED_FUND_SCORE, r$RSI))
  }
} else {
  md <- c(md, "No enhanced fund scores available.\n")
}
md <- c(md, "\n")

# --- Market cap ---
md <- c(md, "## Market cap mix\n\n")
cap_tbl <- buys %>%
  group_by(MARKET_CAP_CATEGORY) %>%
  summarise(n = n(), mean_tech = mean(TECHNICAL_SCORE, na.rm = TRUE), .groups = "drop") %>%
  arrange(desc(mean_tech))
md <- c(md, "| Cap | Count | Avg tech score |\n|-----|-------|----------------|\n")
for (i in seq_len(nrow(cap_tbl))) {
  md <- c(md, sprintf("| %s | %d | %.1f |\n", cap_tbl$MARKET_CAP_CATEGORY[i], cap_tbl$n[i], cap_tbl$mean_tech[i]))
}
md <- c(md, "\n")

# --- Trend alignment ---
md <- c(md, "## Trend signal vs trading signal\n\n")
ch <- buys %>%
  filter(!is.na(TREND_SIGNAL)) %>%
  count(TREND_SIGNAL, name = "n") %>%
  arrange(desc(n))
md <- c(md, md_pipe_table(as.data.frame(ch)), "\n")

bear_trend <- buys$TRADING_SIGNAL %in% c("BUY", "STRONG_BUY") &
  buys$TREND_SIGNAL %in% c("BEARISH", "STRONG_BEARISH")
md <- c(md, sprintf("**BUY / STRONG_BUY but bearish trend label:** **%d** — mixed signals; often pullback or lagging trend metric.\n\n", sum(bear_trend, na.rm = TRUE)))
if (sum(bear_trend) > 0 && sum(bear_trend) <= 25) {
  bt <- buys[bear_trend, ] %>% arrange(desc(TECHNICAL_SCORE))
  md <- c(md, "| Symbol | Tech | Trend | 1M %% |\n|--------|------|-------|------|\n")
  for (i in seq_len(nrow(bt))) {
    md <- c(md, sprintf("| %s | %.1f | %s | %.2f |\n", bt$SYMBOL[i], bt$TECHNICAL_SCORE[i], bt$TREND_SIGNAL[i], bt$CHANGE_1M[i]))
  }
  md <- c(md, "\n")
}

# --- Composite shortlist ---
md <- c(md, "## Composite emphasis (rank)\n\n")
n_fin_fund <- sum(is.finite(buys$ENHANCED_FUND_SCORE))
safe_scale <- function(x) {
  x <- as.numeric(x)
  if (length(x) < 2L || sd(x, na.rm = TRUE) == 0) rep(0, length(x))
  else as.numeric(scale(x))
}
buys2 <- buys %>%
  mutate(
    rs_z = safe_scale(RELATIVE_STRENGTH),
    tech_z = safe_scale(TECHNICAL_SCORE),
    fund_z = if (n_fin_fund > 2L) safe_scale(ENHANCED_FUND_SCORE) else 0,
    composite = tech_z + rs_z + ifelse(n_fin_fund > 2L & is.finite(ENHANCED_FUND_SCORE), fund_z, 0)
  ) %>%
  arrange(desc(composite))

md <- c(md, "Ranked by z-style blend: technical + relative strength (+ fund z when available).\n\n")
md <- c(md, "| Rank | Symbol | Tech | RS%% | Fund | Signal | 1M%% |\n|------|--------|------|-----|------|--------|------|\n")
for (i in seq_len(min(20, nrow(buys2)))) {
  r <- buys2[i, ]
  fz <- if (is.finite(r$ENHANCED_FUND_SCORE)) sprintf("%.1f", r$ENHANCED_FUND_SCORE) else "—"
  md <- c(md, sprintf("| %d | **%s** | %.1f | %.2f | %s | %s | %.2f |\n",
                      i, r$SYMBOL, r$TECHNICAL_SCORE, r$RELATIVE_STRENGTH, fz, r$TRADING_SIGNAL, r$CHANGE_1M))
}
md <- c(md, "\n")

# --- Full BUY list ---
md <- c(md, "## Full STRONG_BUY + BUY list (by technical score)\n\n")
md <- c(md, "| Symbol | Company | Cap | Tech | RSI | RS%% | CAN | Min | Signal | Trend |\n")
md <- c(md, "|--------|---------|-----|------|-----|-----|-----|-----|--------|-------|\n")
for (i in seq_len(nrow(buys))) {
  r <- buys[i, ]
  co <- substr(gsub("\\|", "/", r$COMPANY_NAME), 1, 28)
  md <- c(md, sprintf(
    "| **%s** | %s | %s | %.1f | %.1f | %.2f | %.0f | %.0f | %s | %s |\n",
    r$SYMBOL, co, r$MARKET_CAP_CATEGORY, r$TECHNICAL_SCORE, r$RSI,
    r$RELATIVE_STRENGTH, r$CAN_SLIM_SCORE, r$MINERVINI_SCORE,
    r$TRADING_SIGNAL, r$TREND_SIGNAL
  ))
}

md <- c(md, "\n---\n*Method: descriptive stats on pipeline outputs; not investment advice.*\n")

out <- file.path("reports", sprintf("BUY_Deep_Analysis_%s.md", suffix))
writeLines(md, out)

idx_h2 <- which(grepl("^## ", md))[1]
md_body <- if (!is.na(idx_h2)) {
  md[idx_h2:length(md)]
} else {
  paste("## Result\n\n", paste(md, collapse = ""), sep = "")
}
html_fragment <- commonmark::markdown_html(paste(md_body, collapse = "\n"), extensions = TRUE)
out_html <- file.path("reports", sprintf("BUY_Deep_Analysis_%s.html", suffix))
write_buy_deep_html(out_html, ad, latest_file, html_fragment, n_total, n_buys, n_sb, n_buy)

cat("Deep analysis written:", normalizePath(out), "\n")
cat("HTML report:", normalizePath(out_html), "\n")
cat("BUY+STRONG_BUY count:", n_buys, "\n")
