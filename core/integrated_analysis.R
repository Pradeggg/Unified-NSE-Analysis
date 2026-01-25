# INTEGRATED TECHNICAL & FUNDAMENTAL ANALYSIS
# Combines the daily technical analysis with SuperPerformance fundamental scoring

# ===== INTEGRATED ANALYSIS FUNCTION =====
integrated_analysis <- function(symbol) {
  cat("🔗 Starting Integrated Technical + Fundamental Analysis for", symbol, "\n")
  cat("=" , rep("=", 60), "\n", sep="")
  
  # Step 1: Get Technical Analysis
  cat("📊 Running Technical Analysis...\n")
  tech_result <- analyze_intraday_stock(symbol)
  
  if(is.null(tech_result)) {
    cat("❌ Technical analysis failed for", symbol, "\n")
    return(NULL)
  }
  
  # Step 2: Get Fundamental Analysis (if screener data is available)
  cat("📈 Running Fundamental Analysis...\n")
  fund_result <- NULL
  
  tryCatch({
    # Check if screenerdata.R is available
    if(exists('fn_get_enhanced_fund_score')) {
      fund_result <- fn_get_enhanced_fund_score(symbol)
      cat("✅ Fundamental analysis completed\n")
    } else {
      cat("⚠️ Fundamental analysis not available (screenerdata.R not loaded)\n")
      # Create dummy fundamental result
      fund_result <- data.frame(
        symbol = symbol,
        ENHANCED_FUND_SCORE = 50,
        EARNINGS_QUALITY = 50,
        SALES_GROWTH = 50,
        FINANCIAL_STRENGTH = 50,
        INSTITUTIONAL_BACKING = 50,
        ERROR = "Screener data not available"
      )
    }
  }, error = function(e) {
    cat("⚠️ Fundamental analysis error:", e$message, "\n")
    fund_result <- data.frame(
      symbol = symbol,
      ENHANCED_FUND_SCORE = 50,
      EARNINGS_QUALITY = 50,
      SALES_GROWTH = 50,
      FINANCIAL_STRENGTH = 50,
      INSTITUTIONAL_BACKING = 50,
      ERROR = conditionMessage(e)
    )
  })
  
  # Step 3: Calculate SuperPerformance Score
  tech_score <- tech_result$technical_score
  fund_score <- fund_result$ENHANCED_FUND_SCORE[1]
  superperformance_score <- (tech_score + fund_score) / 2
  
  cat("📊 Technical Score:", tech_score, "/100\n")
  cat("📈 Fundamental Score:", fund_score, "/100\n")
  cat("🚀 SuperPerformance Score:", round(superperformance_score, 1), "/100\n")
  
  # Step 4: Generate Investment Recommendation
  recommendation <- generate_investment_recommendation(tech_score, fund_score, superperformance_score, tech_result, fund_result)
  
  # Step 5: Create integrated result
  integrated_result <- list(
    symbol = symbol,
    analysis_time = Sys.time(),
    technical_analysis = tech_result,
    fundamental_analysis = fund_result,
    scores = list(
      technical = tech_score,
      fundamental = fund_score,
      superperformance = round(superperformance_score, 1)
    ),
    recommendation = recommendation,
    qualifies_superperformance = superperformance_score > 65
  )
  
  # Print summary
  cat("\n🎯 INVESTMENT RECOMMENDATION:\n")
  cat("Overall Rating:", recommendation$rating, "\n")
  cat("Action:", recommendation$action, "\n")
  cat("Risk Level:", recommendation$risk_level, "\n")
  cat("Key Strengths:", paste(recommendation$strengths, collapse = ", "), "\n")
  cat("Key Concerns:", paste(recommendation$concerns, collapse = ", "), "\n")
  
  if(integrated_result$qualifies_superperformance) {
    cat("🌟 QUALIFIES FOR SUPERPERFORMANCE (Score > 65)\n")
  }
  
  return(integrated_result)
}

# ===== INVESTMENT RECOMMENDATION ENGINE =====
generate_investment_recommendation <- function(tech_score, fund_score, super_score, tech_result, fund_result) {
  
  # Determine overall rating and action
  if(super_score >= 75) {
    rating <- "EXCELLENT"
    action <- "STRONG BUY"
    risk_level <- "LOW-MEDIUM"
  } else if(super_score >= 65) {
    rating <- "VERY GOOD"
    action <- "BUY"
    risk_level <- "MEDIUM"
  } else if(super_score >= 55) {
    rating <- "GOOD"
    action <- "ACCUMULATE"
    risk_level <- "MEDIUM"
  } else if(super_score >= 45) {
    rating <- "AVERAGE"
    action <- "HOLD"
    risk_level <- "MEDIUM-HIGH"
  } else if(super_score >= 35) {
    rating <- "BELOW AVERAGE"
    action <- "CAUTIOUS"
    risk_level <- "HIGH"
  } else {
    rating <- "POOR"
    action <- "AVOID"
    risk_level <- "VERY HIGH"
  }
  
  # Identify strengths and concerns
  strengths <- c()
  concerns <- c()
  
  # Technical analysis insights
  if(tech_score >= 60) {
    strengths <- c(strengths, "Strong technical setup")
  } else if(tech_score <= 30) {
    concerns <- c(concerns, "Weak technical indicators")
  }
  
  if(tech_result$score_components$trend >= 50) {
    strengths <- c(strengths, "Positive trend")
  } else {
    concerns <- c(concerns, "Negative trend")
  }
  
  if(tech_result$score_components$volume >= 50) {
    strengths <- c(strengths, "Good volume support")
  } else if(tech_result$score_components$volume <= 30) {
    concerns <- c(concerns, "Low volume activity")
  }
  
  # Fundamental analysis insights
  if(fund_score >= 60) {
    strengths <- c(strengths, "Strong fundamentals")
  } else if(fund_score <= 40) {
    concerns <- c(concerns, "Weak fundamentals")
  }
  
  if("EARNINGS_QUALITY" %in% names(fund_result) && fund_result$EARNINGS_QUALITY[1] >= 60) {
    strengths <- c(strengths, "Good earnings quality")
  }
  
  if("FINANCIAL_STRENGTH" %in% names(fund_result) && fund_result$FINANCIAL_STRENGTH[1] >= 60) {
    strengths <- c(strengths, "Sound financial health")
  }
  
  # Price momentum insights
  if(tech_result$price_change_pct > 2) {
    strengths <- c(strengths, "Strong positive momentum")
  } else if(tech_result$price_change_pct < -2) {
    concerns <- c(concerns, "Negative price momentum")
  }
  
  # Default messages if none found
  if(length(strengths) == 0) strengths <- c("Balanced risk-reward profile")
  if(length(concerns) == 0) concerns <- c("Monitor market conditions")
  
  return(list(
    rating = rating,
    action = action,
    risk_level = risk_level,
    strengths = strengths,
    concerns = concerns,
    score_breakdown = list(
      technical = tech_score,
      fundamental = fund_score,
      overall = super_score
    )
  ))
}

# ===== MULTI-STOCK INTEGRATED ANALYSIS =====
integrated_multi_analysis <- function(symbols, min_superperformance = 65) {
  cat("🚀 Starting Multi-Stock Integrated Analysis\n")
  cat("Symbols:", paste(symbols, collapse = ", "), "\n")
  cat("SuperPerformance Threshold:", min_superperformance, "\n")
  cat("=" , rep("=", 70), "\n", sep="")
  
  results <- list()
  summary_table <- data.frame(
    Symbol = character(),
    SuperPerformance_Score = numeric(),
    Technical_Score = numeric(),
    Fundamental_Score = numeric(),
    Current_Price = numeric(),
    Price_Change_Pct = numeric(),
    Recommendation = character(),
    Risk_Level = character(),
    Qualifies_SP = logical(),
    stringsAsFactors = FALSE
  )
  
  for(symbol in symbols) {
    cat("\n🔍 Analyzing", symbol, "...\n")
    
    result <- integrated_analysis(symbol)
    
    if(!is.null(result)) {
      results[[symbol]] <- result
      
      # Add to summary
      summary_table <- rbind(summary_table, data.frame(
        Symbol = symbol,
        SuperPerformance_Score = result$scores$superperformance,
        Technical_Score = result$scores$technical,
        Fundamental_Score = result$scores$fundamental,
        Current_Price = round(result$technical_analysis$current_price, 2),
        Price_Change_Pct = round(result$technical_analysis$price_change_pct, 2),
        Recommendation = result$recommendation$action,
        Risk_Level = result$recommendation$risk_level,
        Qualifies_SP = result$qualifies_superperformance,
        stringsAsFactors = FALSE
      ))
    }
    
    Sys.sleep(1) # Rate limiting
  }
  
  # Sort by SuperPerformance score
  summary_table <- summary_table[order(summary_table$SuperPerformance_Score, decreasing = TRUE),]
  
  # Filter SuperPerformance stocks
  superperformance_stocks <- summary_table[summary_table$Qualifies_SP == TRUE,]
  
  cat("\n" , rep("=", 70), "\n", sep="")
  cat("📊 INTEGRATED ANALYSIS SUMMARY\n")
  print(summary_table)
  
  if(nrow(superperformance_stocks) > 0) {
    cat("\n🌟 SUPERPERFORMANCE STOCKS (Score >", min_superperformance, "):\n")
    print(superperformance_stocks)
  } else {
    cat("\n❌ No stocks qualify for SuperPerformance threshold\n")
  }
  
  return(list(
    results = results,
    summary = summary_table,
    superperformance_stocks = superperformance_stocks,
    total_analyzed = length(symbols),
    qualified_count = nrow(superperformance_stocks)
  ))
}

# ===== QUICK TEST FUNCTIONS =====
test_integrated_analysis <- function() {
  cat("🧪 Testing Integrated Analysis with RELIANCE\n")
  result <- integrated_analysis("RELIANCE")
  return(result)
}

test_integrated_multi <- function() {
  cat("🧪 Testing Integrated Multi-Analysis\n")
  symbols <- c("RELIANCE", "TCS", "HDFCBANK", "ITC", "INFY")
  result <- integrated_multi_analysis(symbols)
  return(result)
}

# ===== WATCHLIST FUNCTIONALITY =====
create_watchlist <- function(symbols, update_interval_minutes = 30) {
  cat("👀 Creating watchlist for", length(symbols), "stocks\n")
  cat("Symbols:", paste(symbols, collapse = ", "), "\n")
  cat("Update interval:", update_interval_minutes, "minutes\n")
  
  watchlist_file <- paste0("Watchlist_", format(Sys.time(), "%d%m%Y_%H%M"), ".csv")
  
  # Initial analysis
  result <- integrated_multi_analysis(symbols)
  
  # Save to CSV
  write.csv(result$summary, watchlist_file, row.names = FALSE)
  cat("💾 Watchlist saved to:", watchlist_file, "\n")
  
  return(list(
    file = watchlist_file,
    results = result,
    last_updated = Sys.time(),
    update_interval = update_interval_minutes
  ))
}

cat("✅ Integrated Technical + Fundamental Analysis System Loaded\n")
cat("🎯 Available functions:\n")
cat("   - integrated_analysis(symbol)\n")
cat("   - integrated_multi_analysis(symbols)\n")
cat("   - test_integrated_analysis()\n")
cat("   - test_integrated_multi()\n")
cat("   - create_watchlist(symbols)\n")
