# ================================================================================
# UNIFIED ANALYSIS PIPELINE
# ================================================================================
# Purpose: Main orchestration of NSE analysis workflow combining index and stock analysis
# ================================================================================

#' Main analysis pipeline for NSE data
#' @param analysis_type Type of analysis ("index", "stock", or "both")
#' @param force_refresh Boolean to force data refresh
#' @param output_results Boolean to save results to files
#' @param config Analysis configuration
#' @return List containing analysis results
run_nse_analysis_pipeline <- function(analysis_type = "index", 
                                     force_refresh = FALSE, 
                                     output_results = TRUE,
                                     config = list(project = PROJECT_CONFIG, analysis = ANALYSIS_CONFIG, output = OUTPUT_CONFIG)) {
  
  start_time <- Sys.time()
  cat("\n", paste(rep("=", 80), collapse=""), "\n")
  cat("UNIFIED NSE ANALYSIS PIPELINE\n")
  cat(paste(rep("=", 80), collapse=""), "\n")
  cat("Analysis Type:", analysis_type, "\n")
  cat("Start Time:", format(start_time, "%Y-%m-%d %H:%M:%S"), "\n")
  cat(paste(rep("=", 80), collapse=""), "\n\n")
  
  # Initialize results container
  pipeline_results <- list(
    analysis_type = analysis_type,
    start_time = start_time,
    config = config,
    index_results = NULL,
    stock_results = NULL,
    summary = list(),
    errors = character(0)
  )
  
  tryCatch({
    
    # ========================================
    # 1. INDEX ANALYSIS
    # ========================================
    if(analysis_type %in% c("index", "both")) {
      cat("PHASE 1: INDEX ANALYSIS\n")
      cat(paste(rep("-", 40), collapse=""), "\n")
      
      pipeline_results$index_results <- run_index_analysis(
        force_refresh = force_refresh,
        config = config
      )
      
      if(!is.null(pipeline_results$index_results) && pipeline_results$index_results$success) {
        cat("✓ Index analysis completed successfully\n")
        pipeline_results$summary$index_symbols_analyzed <- nrow(pipeline_results$index_results$technical_results)
      } else {
        warning("Index analysis failed")
        pipeline_results$errors <- c(pipeline_results$errors, "Index analysis failed")
      }
      
      cat("\n")
    }
    
    # ========================================
    # 2. STOCK ANALYSIS
    # ========================================
    if(analysis_type %in% c("stock", "both")) {
      cat("PHASE 2: STOCK ANALYSIS\n")
      cat(paste(rep("-", 40), collapse=""), "\n")
      
      pipeline_results$stock_results <- run_stock_analysis(
        force_refresh = force_refresh,
        config = config
      )
      
      if(!is.null(pipeline_results$stock_results) && pipeline_results$stock_results$success) {
        cat("✓ Stock analysis completed successfully\n")
        pipeline_results$summary$stock_symbols_analyzed <- nrow(pipeline_results$stock_results$technical_results)
      } else {
        warning("Stock analysis failed")
        pipeline_results$errors <- c(pipeline_results$errors, "Stock analysis failed")
      }
      
      cat("\n")
    }
    
    # ========================================
    # 3. OUTPUT GENERATION
    # ========================================
    if(output_results) {
      cat("PHASE 3: OUTPUT GENERATION\n")
      cat(paste(rep("-", 40), collapse=""), "\n")
      
      output_success <- generate_analysis_outputs(pipeline_results, config)
      
      if(output_success) {
        cat("✓ Analysis outputs generated successfully\n")
      } else {
        warning("Output generation failed")
        pipeline_results$errors <- c(pipeline_results$errors, "Output generation failed")
      }
      
      cat("\n")
    }
    
    # ========================================
    # 4. PIPELINE SUMMARY
    # ========================================
    end_time <- Sys.time()
    execution_time <- end_time - start_time
    
    pipeline_results$end_time <- end_time
    pipeline_results$execution_time <- execution_time
    pipeline_results$success <- length(pipeline_results$errors) == 0
    
    cat("PIPELINE SUMMARY\n")
    cat(paste(rep("-", 40), collapse=""), "\n")
    cat("Execution Time:", format(execution_time), "\n")
    cat("Total Errors:", length(pipeline_results$errors), "\n")
    
    if(length(pipeline_results$errors) > 0) {
      cat("Error Details:\n")
      for(error in pipeline_results$errors) {
        cat("  •", error, "\n")
      }
    }
    
    cat("Success:", pipeline_results$success, "\n")
    cat(paste(rep("=", 80), collapse=""), "\n")
    
    return(pipeline_results)
    
  }, error = function(e) {
    pipeline_results$errors <- c(pipeline_results$errors, paste("Pipeline error:", e$message))
    pipeline_results$success <- FALSE
    pipeline_results$end_time <- Sys.time()
    
    cat("PIPELINE FAILED\n")
    cat("Error:", e$message, "\n")
    cat(paste(rep("=", 80), collapse=""), "\n")
    
    return(pipeline_results)
  })
}

#' Run index analysis workflow
#' @param force_refresh Boolean to force data refresh
#' @param config Configuration list
#' @return List with index analysis results
run_index_analysis <- function(force_refresh = FALSE, config) {
  
  result <- list(
    success = FALSE,
    symbol_data = NULL,
    historical_data = NULL,
    technical_results = NULL,
    validation = NULL,
    errors = character(0)
  )
  
  tryCatch({
    
    # Load symbol master data
    cat("Loading index symbol master data...\n")
    result$symbol_data <- load_symbol_master(config$project, analysis_type = "index")
    
    if(nrow(result$symbol_data) == 0) {
      stop("No index symbols loaded")
    }
    
    # Load historical data
    cat("Loading NSE index historical data...\n")
    result$historical_data <- load_nse_index_data(config$project, force_refresh = force_refresh)
    
    if(nrow(result$historical_data) == 0) {
      stop("No index historical data loaded")
    }
    
    # Preprocess data
    cat("Preprocessing index data...\n")
    result$historical_data <- preprocess_nse_data(
      result$historical_data, 
      analysis_type = "index", 
      config$analysis
    )
    
    # Validate data quality
    result$validation <- validate_data_quality(result$historical_data, "index")
    
    if(!result$validation$is_valid) {
      stop("Index data validation failed")
    }
    
    # Run technical analysis
    cat("Running technical analysis on index data...\n")
    result$technical_results <- batch_technical_analysis(
      result$symbol_data,
      result$historical_data,
      analysis_type = "index",
      config$analysis
    )
    
    if(nrow(result$technical_results) == 0) {
      stop("No index technical analysis results generated")
    }
    
    # Validate technical results
    if(!validate_technical_results(result$technical_results)) {
      warning("Index technical results validation failed")
    }
    
    result$success <- TRUE
    cat("Index analysis completed successfully\n")
    
    return(result)
    
  }, error = function(e) {
    result$errors <- c(result$errors, paste("Index analysis error:", e$message))
    warning("Index analysis failed:", e$message)
    return(result)
  })
}

#' Run stock analysis workflow
#' @param force_refresh Boolean to force data refresh
#' @param config Configuration list
#' @return List with stock analysis results
run_stock_analysis <- function(force_refresh = FALSE, config) {
  
  result <- list(
    success = FALSE,
    symbol_data = NULL,
    historical_data = NULL,
    technical_results = NULL,
    validation = NULL,
    errors = character(0)
  )
  
  tryCatch({
    
    # Load symbol master data
    cat("Loading stock symbol master data...\n")
    result$symbol_data <- load_symbol_master(config$project, analysis_type = "stock")
    
    if(nrow(result$symbol_data) == 0) {
      stop("No stock symbols loaded")
    }
    
    # Load historical data
    cat("Loading NSE stock historical data...\n")
    result$historical_data <- load_nse_stock_data(config$project, force_refresh = force_refresh)
    
    if(nrow(result$historical_data) == 0) {
      warning("No stock historical data loaded - using sample structure")
      # Continue with empty data for now
    }
    
    # Preprocess data
    if(nrow(result$historical_data) > 0) {
      cat("Preprocessing stock data...\n")
      result$historical_data <- preprocess_nse_data(
        result$historical_data, 
        analysis_type = "stock", 
        config$analysis
      )
      
      # Validate data quality
      result$validation <- validate_data_quality(result$historical_data, "stock")
      
      if(!result$validation$is_valid) {
        stop("Stock data validation failed")
      }
      
      # Run technical analysis
      cat("Running technical analysis on stock data...\n")
      result$technical_results <- batch_technical_analysis(
        result$symbol_data,
        result$historical_data,
        analysis_type = "stock",
        config$analysis
      )
      
      if(nrow(result$technical_results) == 0) {
        warning("No stock technical analysis results generated")
      }
      
      # Validate technical results
      if(nrow(result$technical_results) > 0 && !validate_technical_results(result$technical_results)) {
        warning("Stock technical results validation failed")
      }
    } else {
      cat("Skipping stock technical analysis - no historical data available\n")
      result$technical_results <- data.frame()
    }
    
    result$success <- TRUE
    cat("Stock analysis completed\n")
    
    return(result)
    
  }, error = function(e) {
    result$errors <- c(result$errors, paste("Stock analysis error:", e$message))
    warning("Stock analysis failed:", e$message)
    return(result)
  })
}

#' Generate analysis outputs and reports
#' @param pipeline_results Complete pipeline results
#' @param config Configuration list
#' @return Boolean indicating success
generate_analysis_outputs <- function(pipeline_results, config) {
  
  tryCatch({
    
    timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
    
    # ========================================
    # 1. INDEX OUTPUTS
    # ========================================
    if(!is.null(pipeline_results$index_results) && 
       !is.null(pipeline_results$index_results$technical_results) &&
       nrow(pipeline_results$index_results$technical_results) > 0) {
      
      # Technical analysis results
      index_file <- file.path(
        config$output$output_dir, 
        paste0("index_analysis_", timestamp, ".csv")
      )
      
      write.csv(
        pipeline_results$index_results$technical_results, 
        index_file, 
        row.names = FALSE
      )
      
      cat("Index analysis results saved to:", basename(index_file), "\n")
      
      # Signals file (if configured)
      if(config$output$generate_signals) {
        signals_data <- generate_trading_signals(
          pipeline_results$index_results$technical_results, 
          "index"
        )
        
        signals_file <- file.path(
          config$output$output_dir, 
          paste0("index_signals_", timestamp, ".csv")
        )
        
        write.csv(signals_data, signals_file, row.names = FALSE)
        cat("Index signals saved to:", basename(signals_file), "\n")
      }
    }
    
    # ========================================
    # 2. STOCK OUTPUTS
    # ========================================
    if(!is.null(pipeline_results$stock_results) && 
       !is.null(pipeline_results$stock_results$technical_results) &&
       nrow(pipeline_results$stock_results$technical_results) > 0) {
      
      # Technical analysis results
      stock_file <- file.path(
        config$output$output_dir, 
        paste0("stock_analysis_", timestamp, ".csv")
      )
      
      write.csv(
        pipeline_results$stock_results$technical_results, 
        stock_file, 
        row.names = FALSE
      )
      
      cat("Stock analysis results saved to:", basename(stock_file), "\n")
      
      # Predictions file (if configured)
      if(config$output$generate_predictions) {
        predictions_data <- generate_price_predictions(
          pipeline_results$stock_results$technical_results
        )
        
        predictions_file <- file.path(
          config$output$output_dir, 
          paste0("stock_predictions_", timestamp, ".csv")
        )
        
        write.csv(predictions_data, predictions_file, row.names = FALSE)
        cat("Stock predictions saved to:", basename(predictions_file), "\n")
      }
    }
    
    # ========================================
    # 3. SUMMARY REPORT
    # ========================================
    if(config$output$generate_summary) {
      summary_file <- file.path(
        config$output$output_dir, 
        paste0("analysis_summary_", timestamp, ".txt")
      )
      
      generate_summary_report(pipeline_results, summary_file)
      cat("Summary report saved to:", basename(summary_file), "\n")
    }
    
    return(TRUE)
    
  }, error = function(e) {
    warning("Output generation failed:", e$message)
    return(FALSE)
  })
}

#' Generate trading signals from technical analysis results
#' @param technical_results Technical analysis data frame
#' @param analysis_type Type of analysis for signal generation
#' @return Data frame with trading signals
generate_trading_signals <- function(technical_results, analysis_type = "index") {
  
  # Simple signal generation logic based on technical indicators
  signals <- technical_results %>%
    mutate(
      SIGNAL = case_when(
        PMA >= 4 & VMA >= 3 & RSI > 50 & MACDIND == 1 ~ "BUY",
        PMA <= 2 & VMA <= 1 & RSI < 50 & MACDIND == -1 ~ "SELL",
        TRUE ~ "HOLD"
      ),
      SIGNAL_STRENGTH = (PMA + VMA) / 9,  # Normalized strength score
      TIMESTAMP = format(Sys.Date(), "%Y-%m-%d")
    ) %>%
    select(SYMBOL, TIMESTAMP, SIGNAL, SIGNAL_STRENGTH, RSI, MACDIND, PMA, VMA)
  
  return(signals)
}

#' Generate price predictions from technical analysis results
#' @param technical_results Technical analysis data frame
#' @return Data frame with price predictions
generate_price_predictions <- function(technical_results) {
  
  # Simple prediction logic based on technical indicators and trends
  predictions <- technical_results %>%
    mutate(
      PREDICTION = case_when(
        trend.close > 0 & RSI < 70 & PMA >= 3 ~ "UP",
        trend.close < 0 & RSI > 30 & PMA <= 2 ~ "DOWN",
        TRUE ~ "FLAT"
      ),
      CONFIDENCE = pmin(abs(trend.close) * 10 + SIGNAL_STRENGTH * 50, 100),
      TIMESTAMP = format(Sys.Date(), "%Y-%m-%d")
    ) %>%
    select(SYMBOL, TIMESTAMP, PREDICTION, CONFIDENCE, trend.close, RSI, PMA)
  
  return(predictions)
}

#' Generate comprehensive summary report
#' @param pipeline_results Complete pipeline results
#' @param output_file Path to output summary file
generate_summary_report <- function(pipeline_results, output_file) {
  
  cat("Generating summary report...\n")
  
  report_lines <- c(
    "NSE UNIFIED ANALYSIS PIPELINE SUMMARY",
    paste(rep("=", 50), collapse=""),
    "",
    paste("Analysis Type:", pipeline_results$analysis_type),
    paste("Start Time:", format(pipeline_results$start_time, "%Y-%m-%d %H:%M:%S")),
    paste("End Time:", format(pipeline_results$end_time, "%Y-%m-%d %H:%M:%S")),
    paste("Execution Time:", format(pipeline_results$execution_time)),
    paste("Success:", pipeline_results$success),
    "",
    "RESULTS SUMMARY:",
    paste(rep("-", 20), collapse="")
  )
  
  # Index results summary
  if(!is.null(pipeline_results$index_results)) {
    report_lines <- c(report_lines,
      "",
      "Index Analysis:",
      paste("  Success:", pipeline_results$index_results$success),
      paste("  Symbols Analyzed:", ifelse(is.null(pipeline_results$index_results$technical_results), 0, 
                                         nrow(pipeline_results$index_results$technical_results))),
      paste("  Data Validation:", ifelse(is.null(pipeline_results$index_results$validation), "Not run",
                                        ifelse(pipeline_results$index_results$validation$is_valid, "Passed", "Failed")))
    )
  }
  
  # Stock results summary
  if(!is.null(pipeline_results$stock_results)) {
    report_lines <- c(report_lines,
      "",
      "Stock Analysis:",
      paste("  Success:", pipeline_results$stock_results$success),
      paste("  Symbols Analyzed:", ifelse(is.null(pipeline_results$stock_results$technical_results), 0, 
                                         nrow(pipeline_results$stock_results$technical_results))),
      paste("  Data Validation:", ifelse(is.null(pipeline_results$stock_results$validation), "Not run",
                                        ifelse(pipeline_results$stock_results$validation$is_valid, "Passed", "Failed")))
    )
  }
  
  # Errors summary
  if(length(pipeline_results$errors) > 0) {
    report_lines <- c(report_lines,
      "",
      "ERRORS:",
      paste(rep("-", 10), collapse="")
    )
    
    for(error in pipeline_results$errors) {
      report_lines <- c(report_lines, paste("  •", error))
    }
  }
  
  # Write to file
  writeLines(report_lines, output_file)
}
