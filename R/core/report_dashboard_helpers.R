html_escape <- function(x) {
  x <- as.character(ifelse(is.na(x), "", x))
  x <- gsub("&", "&amp;", x, fixed = TRUE)
  x <- gsub("<", "&lt;", x, fixed = TRUE)
  x <- gsub(">", "&gt;", x, fixed = TRUE)
  x <- gsub('"', "&quot;", x, fixed = TRUE)
  gsub("'", "&#39;", x, fixed = TRUE)
}

safe_mean <- function(x, default = 0) {
  x <- suppressWarnings(as.numeric(x))
  if (length(x) == 0 || all(is.na(x))) return(default)
  mean(x, na.rm = TRUE)
}

safe_count <- function(x) {
  if (length(x) == 0) return(0L)
  sum(x %in% TRUE, na.rm = TRUE)
}

clip_score <- function(x, lower = 0, upper = 100) {
  pmin(pmax(x, lower), upper)
}

fmt_num <- function(x, digits = 1, suffix = "") {
  x <- suppressWarnings(as.numeric(x))
  if (length(x) == 0 || is.na(x)) return("N/A")
  paste0(sprintf(paste0("%.", digits, "f"), x), suffix)
}

fmt_pct <- function(x, digits = 1) {
  x <- suppressWarnings(as.numeric(x))
  if (length(x) == 0 || is.na(x)) return("N/A")
  paste0(ifelse(x >= 0, "+", ""), sprintf(paste0("%.", digits, "f%%"), x))
}

stock_signal_class <- function(signal) {
  signal <- toupper(ifelse(is.na(signal), "", signal))
  if (grepl("BUY", signal)) return("signal-buy")
  if (grepl("SELL", signal)) return("signal-sell")
  if (grepl("WEAK", signal)) return("signal-weak")
  "signal-hold"
}

stock_row_html <- function(stocks_df, group_name, max_rows = 6) {
  if (is.null(stocks_df) || nrow(stocks_df) == 0) {
    return('<div class="no-data">No stocks available.</div>')
  }
  rows <- head(stocks_df, max_rows)
  html <- '<div class="decision-table">'
  for (i in seq_len(nrow(rows))) {
    row <- rows[i, ]
    row_group <- if (".GROUP_NAME" %in% names(rows)) row$.GROUP_NAME else group_name
    group_count <- if (".GROUP_COUNT" %in% names(rows)) suppressWarnings(as.integer(row$.GROUP_COUNT)) else NA_integer_
    more_groups <- if (!is.na(group_count) && group_count > 3) paste0(" +", group_count - 3, " more") else ""
    row_meta <- if (".GROUP_NAME" %in% names(rows)) paste0(group_name, " · ", row_group, more_groups) else row_group
    html <- paste0(
      html,
      '<div class="decision-row" onclick="showStockDetails(\'', html_escape(row$SYMBOL), '\', 0)">',
      '<div><strong>', html_escape(row$SYMBOL), '</strong><span>', html_escape(row_meta), ' · ', html_escape(row$MARKET_CAP_CATEGORY), '</span></div>',
      '<div>', fmt_num(row$TECHNICAL_SCORE, 1), '</div>',
      '<div class="', stock_signal_class(row$TRADING_SIGNAL), '">', html_escape(row$TRADING_SIGNAL), '</div>',
      '<div class="', ifelse(suppressWarnings(as.numeric(row$CHANGE_1M)) >= 0, "positive", "negative"), '">',
      fmt_pct(row$CHANGE_1M, 1), '</div>',
      '</div>'
    )
  }
  paste0(html, '</div>')
}

is_stage2_proxy <- function(stocks_df) {
  trend <- toupper(ifelse(is.na(stocks_df$TREND_SIGNAL), "", stocks_df$TREND_SIGNAL))
  signal <- toupper(ifelse(is.na(stocks_df$TRADING_SIGNAL), "", stocks_df$TRADING_SIGNAL))
  tech <- suppressWarnings(as.numeric(stocks_df$TECHNICAL_SCORE))
  grepl("BULLISH", trend) | grepl("BUY", signal) | (!is.na(tech) & tech >= 70)
}

is_weak_proxy <- function(stocks_df) {
  trend <- toupper(ifelse(is.na(stocks_df$TREND_SIGNAL), "", stocks_df$TREND_SIGNAL))
  signal <- toupper(ifelse(is.na(stocks_df$TRADING_SIGNAL), "", stocks_df$TRADING_SIGNAL))
  tech <- suppressWarnings(as.numeric(stocks_df$TECHNICAL_SCORE))
  grepl("BEARISH", trend) | grepl("SELL", signal) | (!is.na(tech) & tech < 35)
}

group_all_stocks <- function(group_info) {
  if (!is.null(group_info$all_stocks)) return(group_info$all_stocks)
  group_info$stocks
}

build_group_profiles <- function(group_data, group_type = "Sector", performance_lookup = NULL) {
  profiles <- lapply(names(group_data), function(group_name) {
    info <- group_data[[group_name]]
    stocks <- group_all_stocks(info)
    if (is.null(stocks) || nrow(stocks) == 0) return(NULL)

    stage2_flags <- is_stage2_proxy(stocks)
    weak_flags <- is_weak_proxy(stocks)
    buy_flags <- grepl("BUY", toupper(ifelse(is.na(stocks$TRADING_SIGNAL), "", stocks$TRADING_SIGNAL)))
    sell_flags <- grepl("SELL", toupper(ifelse(is.na(stocks$TRADING_SIGNAL), "", stocks$TRADING_SIGNAL)))
    one_month <- suppressWarnings(as.numeric(stocks$CHANGE_1M))
    avg_fund <- safe_mean(if ("ENHANCED_FUND_SCORE" %in% names(stocks)) stocks$ENHANCED_FUND_SCORE else stocks$FUNDAMENTAL_SCORE)

    perf_1m <- safe_mean(one_month)
    if (!is.null(performance_lookup) && !is.null(performance_lookup[[group_name]]) && !is.null(performance_lookup[[group_name]]$perf1M)) {
      perf_1m <- performance_lookup[[group_name]]$perf1M
    }

    avg_tech <- safe_mean(stocks$TECHNICAL_SCORE)
    stage2_pct <- 100 * safe_mean(stage2_flags)
    buy_pct <- 100 * safe_mean(buy_flags)
    breadth_pct <- 100 * safe_mean(one_month > 0)
    return_score <- clip_score(50 + (perf_1m * 2.5))
    leadership_score <- (0.30 * avg_tech) + (0.25 * stage2_pct) + (0.20 * return_score) +
      (0.10 * buy_pct) + (0.10 * avg_fund) + (0.05 * breadth_pct)

    rotation <- if (leadership_score >= 60 && stage2_pct >= 35 && perf_1m >= 0) {
      "Leadership"
    } else if (leadership_score >= 50 && perf_1m >= 0) {
      "Improving"
    } else if (leadership_score >= 50 && perf_1m < 0) {
      "Weakening"
    } else {
      "Lagging"
    }

    data.frame(
      GROUP = group_name,
      GROUP_TYPE = group_type,
      TOTAL_STOCKS = nrow(stocks),
      LEADERSHIP_SCORE = round(leadership_score, 1),
      AVG_TECHNICAL_SCORE = round(avg_tech, 1),
      AVG_FUNDAMENTAL_SCORE = round(avg_fund, 1),
      ONE_MONTH_RETURN = round(perf_1m, 1),
      STAGE2_PCT = round(stage2_pct, 1),
      BUY_PCT = round(buy_pct, 1),
      SELL_PCT = round(100 * safe_mean(sell_flags), 1),
      WEAK_PCT = round(100 * safe_mean(weak_flags), 1),
      BREADTH_PCT = round(breadth_pct, 1),
      ROTATION_BUCKET = rotation,
      stringsAsFactors = FALSE
    )
  })
  profiles <- bind_rows(Filter(Negate(is.null), profiles))
  profiles %>% arrange(desc(LEADERSHIP_SCORE), desc(STAGE2_PCT), desc(ONE_MONTH_RETURN))
}

rule_based_market_narrative <- function(profiles, report_type) {
  if (is.null(profiles) || nrow(profiles) == 0) {
    return("No group-level data was available to generate a market narrative.")
  }
  leaders <- head(profiles$GROUP, 3)
  laggards <- tail(profiles$GROUP, min(3, nrow(profiles)))
  leadership_count <- safe_count(profiles$ROTATION_BUCKET == "Leadership")
  improving_count <- safe_count(profiles$ROTATION_BUCKET == "Improving")
  weak_count <- safe_count(profiles$ROTATION_BUCKET %in% c("Weakening", "Lagging"))
  paste0(
    report_type, " leadership is concentrated in ", paste(leaders, collapse = ", "),
    ". ", leadership_count, " groups are in Leadership and ", improving_count,
    " are Improving, while ", weak_count, " remain Weakening or Lagging. ",
    "The weakest pockets are ", paste(rev(laggards), collapse = ", "),
    ". Prioritize groups with high leadership score, positive one-month breadth, and strong Stage 2 proxy participation; treat SELL-heavy groups as risk controls."
  )
}

llm_market_narrative <- function(profiles, report_type) {
  fallback <- rule_based_market_narrative(profiles, report_type)
  model <- Sys.getenv("OLLAMA_MODEL", unset = "")
  if (model == "" || Sys.getenv("REPORT_LLM_NARRATIVE", unset = "1") == "0") {
    return(list(text = fallback, source = "Rule-based narrative"))
  }
  curl <- Sys.which("curl")
  if (!nzchar(curl)) {
    return(list(text = fallback, source = "Rule-based narrative; curl unavailable for Ollama"))
  }
  sample_profiles <- profiles %>%
    select(GROUP, LEADERSHIP_SCORE, AVG_TECHNICAL_SCORE, ONE_MONTH_RETURN, STAGE2_PCT, BUY_PCT, SELL_PCT, BREADTH_PCT, ROTATION_BUCKET) %>%
    head(12)
  prompt <- paste(
    "Write a concise NSE market intelligence narrative for this", report_type, "dashboard.",
    "Use only the supplied JSON. Do not give investment advice, price targets, or buy/sell instructions.",
    "Cover leadership, rotation, breadth, risks, and what to monitor next in 4-6 sentences.",
    toJSON(sample_profiles, dataframe = "rows", auto_unbox = TRUE),
    sep = "\n"
  )
  payload <- toJSON(list(model = model, prompt = prompt, stream = FALSE, options = list(temperature = 0.25)), auto_unbox = TRUE)
  host <- Sys.getenv("OLLAMA_HOST", unset = "http://127.0.0.1:11434")
  tmp <- tempfile()
  status <- suppressWarnings(system2(curl, c("-sS", "--max-time", "90", "-H", "Content-Type: application/json", "-d", "@-", paste0(sub("/+$", "", host), "/api/generate")), input = payload, stdout = tmp, stderr = FALSE))
  if (!identical(status, 0L) || !file.exists(tmp) || file.info(tmp)$size == 0) {
    return(list(text = fallback, source = paste("Rule-based narrative; Ollama", model, "unavailable")))
  }
  parsed <- tryCatch(fromJSON(tmp), error = function(e) NULL)
  narrative <- if (!is.null(parsed) && !is.null(parsed$response)) trimws(parsed$response) else ""
  if (narrative == "") {
    return(list(text = fallback, source = paste("Rule-based narrative; Ollama", model, "returned empty response")))
  }
  list(text = narrative, source = paste("LLM narrative via Ollama", model))
}

leadership_table_html <- function(profiles, limit = 12) {
  rows <- head(profiles, limit)
  html <- '<div class="leadership-table"><div class="leadership-row leadership-head"><div>Rank</div><div>Group</div><div>Score</div><div>Stage 2%</div><div>1M</div><div>BUY%</div><div>Bucket</div></div>'
  for (i in seq_len(nrow(rows))) {
    bucket_class <- paste0("bucket-", tolower(rows$ROTATION_BUCKET[i]))
    html <- paste0(
      html,
      '<div class="leadership-row"><div>#', i, '</div><div><strong>', html_escape(rows$GROUP[i]), '</strong></div>',
      '<div>', fmt_num(rows$LEADERSHIP_SCORE[i], 1), '</div>',
      '<div>', fmt_num(rows$STAGE2_PCT[i], 0, "%"), '</div>',
      '<div class="', ifelse(rows$ONE_MONTH_RETURN[i] >= 0, "positive", "negative"), '">', fmt_pct(rows$ONE_MONTH_RETURN[i], 1), '</div>',
      '<div>', fmt_num(rows$BUY_PCT[i], 0, "%"), '</div>',
      '<div class="bucket ', bucket_class, '">', rows$ROTATION_BUCKET[i], '</div></div>'
    )
  }
  paste0(html, '</div>')
}

rotation_quadrant_html <- function(profiles) {
  buckets <- c("Leadership", "Improving", "Weakening", "Lagging")
  html <- '<div class="rotation-grid">'
  for (bucket in buckets) {
    groups <- profiles %>% filter(ROTATION_BUCKET == bucket) %>% arrange(desc(LEADERSHIP_SCORE)) %>% head(8)
    items <- if (nrow(groups) == 0) {
      '<span class="muted">No groups</span>'
    } else {
      paste0('<span>', html_escape(groups$GROUP), ' <em>', sprintf("%.1f", groups$LEADERSHIP_SCORE), '</em></span>', collapse = "")
    }
    html <- paste0(html, '<div class="rotation-card bucket-', tolower(bucket), '"><h4>', bucket, '</h4><div class="rotation-items">', items, '</div></div>')
  }
  paste0(html, '</div>')
}

watchlist_html <- function(group_data, group_name_field = "Group") {
  all_rows <- bind_rows(lapply(names(group_data), function(group_name) {
    stocks <- group_all_stocks(group_data[[group_name]])
    if (is.null(stocks) || nrow(stocks) == 0) return(NULL)
    stocks %>% mutate(.GROUP_NAME = group_name)
  }))
  if (is.null(all_rows) || nrow(all_rows) == 0) return("")

  dedupe_watchlist <- function(rows) {
    if (is.null(rows) || nrow(rows) == 0) return(rows)
    rows %>%
      mutate(.ROW_ORDER = row_number()) %>%
      group_by(SYMBOL) %>%
      mutate(
        .GROUP_COUNT = n_distinct(.GROUP_NAME),
        .GROUP_NAME = paste(head(unique(.GROUP_NAME), 3), collapse = ", ")
      ) %>%
      slice(1) %>%
      ungroup() %>%
      arrange(.ROW_ORDER) %>%
      select(-.ROW_ORDER)
  }

  breakout <- all_rows %>%
    filter(is_stage2_proxy(.), suppressWarnings(as.numeric(TECHNICAL_SCORE)) >= 70) %>%
    arrange(desc(TECHNICAL_SCORE), desc(CHANGE_1M)) %>%
    dedupe_watchlist() %>%
    head(8)
  pullback <- all_rows %>%
    filter(is_stage2_proxy(.), suppressWarnings(as.numeric(CHANGE_1D)) < 0, suppressWarnings(as.numeric(CHANGE_1M)) > 0) %>%
    arrange(desc(TECHNICAL_SCORE)) %>%
    dedupe_watchlist() %>%
    head(8)
  improving <- all_rows %>%
    filter(grepl("HOLD|BUY", toupper(ifelse(is.na(TRADING_SIGNAL), "", TRADING_SIGNAL))), suppressWarnings(as.numeric(CHANGE_1M)) > 0) %>%
    arrange(desc(CHANGE_1M), desc(TECHNICAL_SCORE)) %>%
    dedupe_watchlist() %>%
    head(8)
  avoid <- all_rows %>%
    filter(is_weak_proxy(.)) %>%
    arrange(TECHNICAL_SCORE, CHANGE_1M) %>%
    dedupe_watchlist() %>%
    head(8)

  paste0(
    '<div class="section-card"><h2>Actionable Watchlists</h2><p class="section-note">Deterministic screens for monitoring; not trade recommendations.</p>',
    '<div class="watchlist-grid">',
    '<div class="screener-card"><div class="screener-header"><h3>Breakout / Leadership Watch</h3><p>High technical score with constructive trend proxy.</p></div>', stock_row_html(breakout, group_name_field, 8), '</div>',
    '<div class="screener-card"><div class="screener-header"><h3>Stage 2 Pullback Watch</h3><p>Positive one-month profile with short-term softness.</p></div>', stock_row_html(pullback, group_name_field, 8), '</div>',
    '<div class="screener-card"><div class="screener-header"><h3>Improving Momentum</h3><p>Positive one-month change and improving signal quality.</p></div>', stock_row_html(improving, group_name_field, 8), '</div>',
    '<div class="screener-card"><div class="screener-header"><h3>Risk / Avoid Monitor</h3><p>Weak trend, SELL signal, or low technical score.</p></div>', stock_row_html(avoid, group_name_field, 8), '</div>',
    '</div></div>'
  )
}

dashboard_css <- '
        .section-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); padding: 18px; margin: 16px 0; }
        .section-card h2 { color: var(--primary); font-size: 1.1rem; font-weight: 800; margin-bottom: 6px; }
        .section-note, .muted { color: var(--muted); font-size: 12px; }
        .narrative-box { background: #f8fbff; border-left: 4px solid var(--primary-alt); padding: 14px 16px; border-radius: 8px; margin-top: 12px; }
        .narrative-source { color: var(--muted); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; margin-top: 8px; }
        .leadership-table { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-top: 12px; }
        .leadership-row { display: grid; grid-template-columns: 60px 1.7fr repeat(5, 1fr); gap: 8px; align-items: center; padding: 9px 12px; border-bottom: 1px solid var(--border); background: #fff; font-size: 12px; }
        .leadership-row:last-child { border-bottom: 0; }
        .leadership-head { background: #eef4fb; color: var(--primary); font-weight: 800; text-transform: uppercase; letter-spacing: .05em; font-size: 10px; }
        .bucket { display: inline-flex; width: fit-content; border-radius: 14px; padding: 3px 8px; font-size: 10px; font-weight: 800; text-transform: uppercase; }
        .bucket-leadership { background: #dcfce7; color: #166534; }
        .bucket-improving { background: #dbeafe; color: #1e40af; }
        .bucket-weakening { background: #fef3c7; color: #92400e; }
        .bucket-lagging { background: #fee2e2; color: #991b1b; }
        .rotation-grid, .watchlist-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 12px; }
        .rotation-card { border: 1px solid var(--border); border-radius: 8px; padding: 13px; background: #fff; }
        .rotation-card h4 { color: var(--primary); font-size: 12px; font-weight: 900; text-transform: uppercase; margin-bottom: 8px; }
        .rotation-items { display: flex; flex-wrap: wrap; gap: 6px; }
        .rotation-items span { background: #f8fafc; border: 1px solid var(--border); border-radius: 16px; padding: 4px 8px; font-size: 11px; font-weight: 700; }
        .rotation-items em { color: var(--muted); font-style: normal; font-weight: 800; }
        .group-metrics { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
        .decision-table { margin-top: 10px; border-top: 1px solid var(--border); }
        .decision-row { display: grid; grid-template-columns: 1.8fr .7fr .9fr .7fr; gap: 8px; align-items: center; border-bottom: 1px solid var(--border); padding: 8px 0; font-size: 12px; cursor: pointer; }
        .decision-row span { display: block; color: var(--muted); font-size: 10px; margin-top: 2px; }
        .signal-buy, .positive { color: #15803d; font-weight: 800; }
        .signal-sell, .negative { color: #b91c1c; font-weight: 800; }
        .signal-hold { color: #92400e; font-weight: 800; }
        .signal-weak { color: #c2410c; font-weight: 800; }
        @media (max-width: 800px) { .leadership-row { grid-template-columns: 45px 1.5fr 1fr 1fr; } .leadership-row div:nth-child(n+5) { display: none; } .decision-row { grid-template-columns: 1.4fr .6fr .8fr; } .decision-row div:nth-child(4) { display: none; } }
'

dashboard_html <- function(group_data, profiles, report_type) {
  narrative <- llm_market_narrative(profiles, report_type)
  leaders <- head(profiles, 3)
  weak <- profiles %>% arrange(LEADERSHIP_SCORE) %>% head(3)
  paste0(
    '<div class="section-card"><h2>Executive Summary</h2>',
    '<p class="section-note">Leadership, rotation, breadth, and risk are computed from PostgreSQL-backed daily scores.</p>',
    '<div class="narrative-box">', html_escape(narrative$text), '<div class="narrative-source">', html_escape(narrative$source), '</div></div>',
    '<div class="summary-grid" style="margin-top: 12px; margin-bottom: 0;">',
    '<div class="summary-card"><div class="number">', html_escape(leaders$GROUP[1]), '</div><p>Top Leadership Group</p></div>',
    '<div class="summary-card"><div class="number">', fmt_num(leaders$LEADERSHIP_SCORE[1], 1), '</div><p>Leadership Score</p></div>',
    '<div class="summary-card"><div class="number">', safe_count(profiles$ROTATION_BUCKET == "Leadership"), '</div><p>Leadership Buckets</p></div>',
    '<div class="summary-card"><div class="number">', html_escape(weak$GROUP[1]), '</div><p>Weakest Group</p></div>',
    '</div></div>',
    '<div class="section-card"><h2>Leadership Ranking</h2><p class="section-note">Composite score = technical strength, Stage 2 proxy participation, 1M return, signal quality, fundamentals, and breadth.</p>',
    leadership_table_html(profiles, 14), '</div>',
    '<div class="section-card"><h2>Rotation Map</h2><p class="section-note">Groups are classified into Leadership, Improving, Weakening, or Lagging from leadership score, trend proxy, and one-month return.</p>',
    rotation_quadrant_html(profiles), '</div>',
    watchlist_html(group_data, report_type)
  )
}
