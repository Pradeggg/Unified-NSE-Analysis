# COMPREHENSIVE FUNDAMENTAL SCORES GENERATOR
# This script computes fundamental scores for ALL NSE stocks and stores them in CSV format
# Run this script periodically (weekly/monthly) to update fundamental scores

suppressMessages({
  library(dplyr)
  library(stringr)
  library(rvest)
})

# Source the enhanced fundamental scoring functions
tryCatch({
  if(file.exists("Unified-NSE-Analysis/core/screenerdata.R")) {
    source("Unified-NSE-Analysis/core/screenerdata.R")
    cat("✓ Loaded enhanced fundamental scoring functions from screenerdata.R\n")
  } else if(file.exists("screenerdata.R")) {
    source("screenerdata.R")
    cat("✓ Loaded fundamental scoring functions from screenerdata.R\n")
  } else {
    stop("❌ Error: screenerdata.R not found - fundamental scoring functions required")
  }
}, error = function(e) {
  stop("❌ Error loading screenerdata.R: ", conditionMessage(e))
})

# Color formatting functions
format_info <- function(text) paste0("\033[34m", text, "\033[0m")
format_success <- function(text) paste0("\033[32m", text, "\033[0m")
format_warning <- function(text) paste0("\033[33m", text, "\033[0m")
format_value <- function(text) paste0("\033[1;36m", text, "\033[0m")
format_error <- function(text) paste0("\033[31m", text, "\033[0m")

cat("🏭 COMPREHENSIVE FUNDAMENTAL SCORES GENERATOR\n")
cat("═══════════════════════════════════════════════════════════\n")

# Check if fundamental scoring function exists
if(!exists('fn_get_enhanced_fund_score')) {
  stop("❌ Error: fn_get_enhanced_fund_score function not found")
}

# Load all unique stocks from NSE data
cat(format_info("📂 Loading NSE stock data...\n"))
stock_file <- "NSE-index/nse_sec_full_data.csv"

if(!file.exists(stock_file)) {
  stop("❌ Error: NSE stock data file not found: ", stock_file)
}

stock_data_raw <- read.csv(stock_file, stringsAsFactors = FALSE, header = FALSE)
colnames(stock_data_raw) <- c("SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES")
stock_data <- stock_data_raw[-1, ]

# Get unique stocks
unique_stocks <- unique(stock_data$SYMBOL)
unique_stocks <- unique_stocks[!is.na(unique_stocks) & unique_stocks != ""]
unique_stocks <- sort(unique_stocks)

cat(format_success("✓ Found"), format_value(length(unique_stocks)), format_success("unique stocks in NSE data\n"))

# Check if previous fundamental scores exist
output_file <- "fundamental_scores_database.csv"
existing_scores <- data.frame()
new_stocks_to_process <- unique_stocks

if(file.exists(output_file)) {
  existing_scores <- read.csv(output_file, stringsAsFactors = FALSE)
  cat(format_info("📊 Found existing fundamental scores:"), format_value(nrow(existing_scores)), format_info("stocks\n"))
  
  # Only process stocks not in existing database
  existing_symbols <- unique(existing_scores$symbol)
  new_stocks_to_process <- setdiff(unique_stocks, existing_symbols)
  
  if(length(new_stocks_to_process) == 0) {
    cat(format_success("✅ All stocks already have fundamental scores! Database is up to date.\n"))
    cat(format_info("💡 To refresh all scores, delete"), format_value(output_file), format_info("and run this script again.\n"))
    quit(save = "no")
  }
  
  cat(format_info("🔄 Need to process"), format_value(length(new_stocks_to_process)), format_info("new stocks\n"))
} else {
  cat(format_info("🆕 Creating new fundamental scores database\n"))
  cat(format_info("🔗 Enhanced rate limiting enabled to prevent connection overload\n"))
}

# Progress tracking
total_stocks <- length(new_stocks_to_process)
fundamental_scores_list <- list()
successful_scores <- 0
failed_scores <- 0
start_time <- Sys.time()

cat(format_info("\n🎯 Processing"), format_value(total_stocks), format_info("stocks for fundamental analysis...\n"))
cat(format_warning("⏱️ Estimated time:"), format_value(paste0(round(total_stocks * 4.5 / 60, 1), " minutes")), "\n")
cat(format_info("🔗 Enhanced connection management enabled\n"))
cat("═══════════════════════════════════════════════════════════\n")

# Enhanced batch processing with connection management
BATCH_SIZE <- 25  # Process in smaller batches
current_batch <- 1
total_batches <- ceiling(total_stocks / BATCH_SIZE)
connection_monitor_interval <- 10  # Monitor connections every 10 stocks

# Connection monitoring function
monitor_connections <- function() {
  tryCatch({
    # Check if we can query connection status
    conn_info <- showConnections(all = TRUE)
    active_connections <- nrow(conn_info)
    if(active_connections > 0) {
      cat(format_warning(paste0(" [Connections: ", active_connections, "]")))
    }
  }, error = function(e) {
    # Connection monitoring failed, not critical
  })
}

# Process each stock
for(i in seq_along(new_stocks_to_process)) {
  symbol <- new_stocks_to_process[i]
  progress_pct <- round((i/total_stocks) * 100, 1)
  
  # Progress display
  elapsed_time <- as.numeric(difftime(Sys.time(), start_time, units = "mins"))
  est_total_time <- if(i > 5) elapsed_time / i * total_stocks else NA
  eta_mins <- if(!is.na(est_total_time)) max(0, est_total_time - elapsed_time) else NA
  
  progress_text <- paste0(
    format_info("📈 ["), format_value(sprintf("%d/%d", i, total_stocks)), 
    format_info("] ("), format_value(paste0(progress_pct, "%")), format_info(") "),
    format_value(symbol)
  )
  
  if(!is.na(eta_mins)) {
    progress_text <- paste0(progress_text, format_info(" - ETA: "), 
                           format_value(paste0(round(eta_mins, 1), "min")))
  }
  
  # Add connection monitoring
  if(i %% connection_monitor_interval == 0) {
    monitor_connections()
  }
  
  cat(progress_text, "                              \r")
  flush.console()
  
  # Get fundamental score with enhanced error handling and retry logic
  max_retries <- 3
  retry_count <- 0
  fund_data <- NULL
  
  while(retry_count < max_retries && is.null(fund_data)) {
    tryCatch({
      # Add small delay before each attempt
      if(retry_count > 0) {
        cat(format_warning(paste0("\n🔄 Retry ", retry_count, "/", max_retries-1, " for ", symbol)))
        Sys.sleep(2 * retry_count)  # Exponential backoff
      }
      
      fund_data <- fn_get_enhanced_fund_score(symbol)
      
      if(!is.null(fund_data) && nrow(fund_data) > 0) {
        # Add processing timestamp
        fund_data$processed_date <- Sys.Date()
        fund_data$processing_batch <- format(Sys.time(), "%Y%m%d_%H%M")
        fund_data$batch_number <- current_batch
        
        fundamental_scores_list[[symbol]] <- fund_data
        successful_scores <- successful_scores + 1
        break  # Success, exit retry loop
      } else {
        fund_data <- NULL  # Ensure we retry
        retry_count <- retry_count + 1
      }
      
    }, error = function(e) {
      error_msg <- conditionMessage(e)
      
      # Check for connection-related errors
      if(grepl("connection|timeout|curl|socket", error_msg, ignore.case = TRUE)) {
        cat(format_warning(paste0("\n⚠️ Connection error for ", symbol, ": ", substr(error_msg, 1, 50))))
        retry_count <<- retry_count + 1
        
        if(retry_count < max_retries) {
          cat(format_info(" - Will retry..."))
          Sys.sleep(5)  # Wait longer for connection errors
        }
      } else {
        # Non-connection error, don't retry
        retry_count <<- max_retries
        cat(format_error(paste0("\n❌ Non-recoverable error for ", symbol, ": ", substr(error_msg, 1, 50))))
      }
    })
  }
  
  # Handle final result or create default entry
  if(is.null(fund_data) || (exists("fund_data") && (is.null(fund_data) || nrow(fund_data) == 0))) {
    # Create default entry for failed stocks
    default_entry <- data.frame(
      symbol = symbol,
      ENHANCED_FUND_SCORE = 25,  # Conservative default
      EARNINGS_QUALITY = "Poor",
      SALES_GROWTH = "Low", 
      FINANCIAL_STRENGTH = "Weak",
      INSTITUTIONAL_BACKING = "Low",
      processed_date = Sys.Date(),
      processing_batch = format(Sys.time(), "%Y%m%d_%H%M"),
      batch_number = current_batch,
      error_reason = "No data available after retries",
      stringsAsFactors = FALSE
    )
    fundamental_scores_list[[symbol]] <- default_entry
    failed_scores <- failed_scores + 1
  }
  
  # Update batch progress
  if(i %% BATCH_SIZE == 0 || i == total_stocks) {
    cat(format_success(paste0("\n✅ Batch ", current_batch, "/", total_batches, " completed")))
    current_batch <- current_batch + 1
  }
  
    # Save progress every 50 stocks or at batch completion
    if(i %% 50 == 0 || i %% BATCH_SIZE == 0) {
      cat(format_info("\n💾 Saving progress... ("), format_value(successful_scores), 
          format_info("successful,"), format_value(failed_scores), format_info("failed)\n"))
      
      # Combine with existing scores and save
      if(length(fundamental_scores_list) > 0) {
        # Ensure all data frames have consistent column structure
        required_columns <- c("symbol", "ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "SALES_GROWTH", 
                             "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING", "processed_date", 
                             "processing_batch", "batch_number")
        
        # Standardize each data frame in the list
        standardized_list <- list()
        for(stock_name in names(fundamental_scores_list)) {
          df <- fundamental_scores_list[[stock_name]]
          
          # Ensure all required columns exist
          for(col in required_columns) {
            if(!col %in% names(df)) {
              if(col == "symbol") {
                df[[col]] <- stock_name
              } else if(col %in% c("ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "SALES_GROWTH", "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING")) {
                df[[col]] <- 25  # Default score
              } else if(col == "processed_date") {
                df[[col]] <- Sys.Date()
              } else if(col == "processing_batch") {
                df[[col]] <- format(Sys.time(), "%Y%m%d_%H%M")
              } else if(col == "batch_number") {
                df[[col]] <- current_batch
              } else {
                df[[col]] <- NA
              }
            }
          }
          
          # Select only required columns in correct order
          standardized_list[[stock_name]] <- df[, required_columns, drop = FALSE]
        }
        
        # Now safely combine the standardized data frames
        new_scores_df <- do.call(rbind, standardized_list)
        rownames(new_scores_df) <- NULL
        
        # Ensure existing scores have the same column structure
        existing_scores_standardized <- existing_scores
        for(col in required_columns) {
          if(!col %in% names(existing_scores_standardized)) {
            if(col %in% c("batch_number")) {
              existing_scores_standardized[[col]] <- 1  # Default batch
            } else {
              existing_scores_standardized[[col]] <- NA
            }
          }
        }
        
        # Select only required columns from existing scores
        if(nrow(existing_scores_standardized) > 0) {
          existing_cols <- intersect(required_columns, names(existing_scores_standardized))
          existing_scores_standardized <- existing_scores_standardized[, existing_cols, drop = FALSE]
          
          # Add missing columns to existing scores
          for(col in setdiff(required_columns, names(existing_scores_standardized))) {
            if(col == "batch_number") {
              existing_scores_standardized[[col]] <- 1
            } else {
              existing_scores_standardized[[col]] <- NA
            }
          }
          
          # Reorder columns
          existing_scores_standardized <- existing_scores_standardized[, required_columns, drop = FALSE]
        }
        
        combined_scores <- if(nrow(existing_scores_standardized) > 0) {
          rbind(existing_scores_standardized, new_scores_df)
        } else {
          new_scores_df
        }
        
        write.csv(combined_scores, output_file, row.names = FALSE)
      }
    }  # Enhanced delay system to prevent connection overload
  if(i %% 5 == 0) {
    # Short pause every 5 stocks
    Sys.sleep(0.5)
    cat(format_info("\n⏸️ Brief pause..."))
    flush.console()
  }
  
  if(i %% 25 == 0) {
    # Longer pause every 25 stocks to let connections close
    cat(format_warning("\n⏳ Extended pause (5 sec) - releasing connections..."))
    Sys.sleep(5)
    gc()  # Garbage collection to free memory
    flush.console()
  }
  
  if(i %% 100 == 0) {
    # Major pause every 100 stocks
    cat(format_warning("\n🔄 Major pause (10 sec) - connection cleanup..."))
    Sys.sleep(10)
    gc()
    flush.console()
  }
}

# Final processing and save
cat(format_success("\n\n✅ PROCESSING COMPLETED!\n"))
cat("═══════════════════════════════════════════════════════════\n")

if(length(fundamental_scores_list) > 0) {
  # Ensure all data frames have consistent column structure for final processing
  required_columns <- c("symbol", "ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "SALES_GROWTH", 
                       "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING", "processed_date", 
                       "processing_batch", "batch_number")
  
  # Standardize each data frame in the list
  standardized_list <- list()
  for(stock_name in names(fundamental_scores_list)) {
    df <- fundamental_scores_list[[stock_name]]
    
    # Ensure all required columns exist
    for(col in required_columns) {
      if(!col %in% names(df)) {
        if(col == "symbol") {
          df[[col]] <- stock_name
        } else if(col %in% c("ENHANCED_FUND_SCORE", "EARNINGS_QUALITY", "SALES_GROWTH", "FINANCIAL_STRENGTH", "INSTITUTIONAL_BACKING")) {
          df[[col]] <- 25  # Default score
        } else if(col == "processed_date") {
          df[[col]] <- Sys.Date()
        } else if(col == "processing_batch") {
          df[[col]] <- format(Sys.time(), "%Y%m%d_%H%M")
        } else if(col == "batch_number") {
          df[[col]] <- current_batch
        } else {
          df[[col]] <- NA
        }
      }
    }
    
    # Select only required columns in correct order
    standardized_list[[stock_name]] <- df[, required_columns, drop = FALSE]
  }
  
  # Combine all new scores
  new_scores_df <- do.call(rbind, standardized_list)
  rownames(new_scores_df) <- NULL
  
  # Combine with existing scores
  existing_scores_standardized <- existing_scores
  for(col in required_columns) {
    if(!col %in% names(existing_scores_standardized)) {
      if(col == "batch_number") {
        existing_scores_standardized[[col]] <- 1  # Default batch
      } else {
        existing_scores_standardized[[col]] <- NA
      }
    }
  }
  
  # Select only required columns from existing scores
  if(nrow(existing_scores_standardized) > 0) {
    existing_cols <- intersect(required_columns, names(existing_scores_standardized))
    existing_scores_standardized <- existing_scores_standardized[, existing_cols, drop = FALSE]
    
    # Add missing columns to existing scores
    for(col in setdiff(required_columns, names(existing_scores_standardized))) {
      if(col == "batch_number") {
        existing_scores_standardized[[col]] <- 1
      } else {
        existing_scores_standardized[[col]] <- NA
      }
    }
    
    # Reorder columns
    existing_scores_standardized <- existing_scores_standardized[, required_columns, drop = FALSE]
  }
  
  final_scores <- if(nrow(existing_scores_standardized) > 0) {
    rbind(existing_scores_standardized, new_scores_df)
  } else {
    new_scores_df
  }
  
  # Remove duplicates (keep latest)
  final_scores <- final_scores %>%
    arrange(symbol, desc(processed_date)) %>%
    distinct(symbol, .keep_all = TRUE)
  
  # Save final database
  write.csv(final_scores, output_file, row.names = FALSE)
  
  # Generate summary report
  summary_stats <- final_scores %>%
    summarise(
      total_stocks = n(),
      avg_fund_score = round(mean(ENHANCED_FUND_SCORE, na.rm = TRUE), 1),
      high_scores = sum(ENHANCED_FUND_SCORE >= 70, na.rm = TRUE),
      good_scores = sum(ENHANCED_FUND_SCORE >= 50 & ENHANCED_FUND_SCORE < 70, na.rm = TRUE),
      poor_scores = sum(ENHANCED_FUND_SCORE < 50, na.rm = TRUE),
      latest_batch = max(processed_date, na.rm = TRUE)
    )
  
  cat(format_success("📊 FINAL DATABASE STATISTICS:\n"))
  cat(format_info("   • Total stocks in database:"), format_value(summary_stats$total_stocks), "\n")
  cat(format_info("   • Average fundamental score:"), format_value(summary_stats$avg_fund_score), "\n")
  cat(format_info("   • High scores (≥70):"), format_value(summary_stats$high_scores), "\n")
  cat(format_info("   • Good scores (50-69):"), format_value(summary_stats$good_scores), "\n")
  cat(format_info("   • Poor scores (<50):"), format_value(summary_stats$poor_scores), "\n")
  cat(format_info("   • Latest processing date:"), format_value(summary_stats$latest_batch), "\n")
  
  cat(format_success("\n✓ Database saved to:"), format_value(output_file), "\n")
  
  # Processing summary
  total_processing_time <- as.numeric(difftime(Sys.time(), start_time, units = "mins"))
  cat(format_info("\n⏱️ PROCESSING SUMMARY:\n"))
  cat(format_info("   • Successfully processed:"), format_value(successful_scores), "\n")
  cat(format_info("   • Failed/default scores:"), format_value(failed_scores), "\n")
  cat(format_info("   • Total processing time:"), format_value(paste0(round(total_processing_time, 1), " minutes")), "\n")
  cat(format_info("   • Average time per stock:"), format_value(paste0(round(total_processing_time/total_stocks*60, 1), " seconds")), "\n")
  
  cat(format_success("\n🎉 Fundamental scores database generation completed successfully!\n"))
  cat(format_info("💡 Use this database in sequential_enhanced_analysis.R for fast fundamental filtering\n"))
  
} else {
  cat(format_error("❌ No fundamental scores were generated\n"))
}
