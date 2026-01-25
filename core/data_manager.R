# ================================================================================
# UNIFIED DATA MANAGER
# ================================================================================
# Purpose: Centralized data loading, caching, and preprocessing for NSE analysis
# ================================================================================

#' Load and cache NSE index data
#' @param config Project configuration list
#' @param force_refresh Boolean to force data refresh
#' @return Data frame with NSE index data
load_nse_index_data <- function(config = PROJECT_CONFIG, force_refresh = FALSE) {
  
  cache_file <- file.path(config$paths$dirs$data, "nse_index_cache.RData")
  
  # Check if cached data exists and is recent
  if(!force_refresh && file.exists(cache_file)) {
    load(cache_file)
    
    if(exists("nse_index_data") && nrow(nse_index_data) > 0) {
      latest_date <- max(as.Date(nse_index_data$TIMESTAMP), na.rm = TRUE)
      
      if(Sys.Date() - latest_date <= 1) {
        cat("Loading NSE index data from cache (latest:", as.character(latest_date), ")\n")
        return(nse_index_data)
      }
    }
  }
  
  cat("Loading fresh NSE index data...\n")
  
  tryCatch({
    # Load the helpers.R file which contains data loading functions
    source(file.path(config$paths$legacy_data, "helpers.R"))
    
    # Get index data using the available function
    # The helpers.R file already loads nse_index_data.csv into dt.NSE.idx
    nse_index_data <- dt.NSE.idx
    
    if(nrow(nse_index_data) > 0) {
      # Cache the data
      save(nse_index_data, file = cache_file)
      cat("NSE index data loaded and cached:", nrow(nse_index_data), "records\n")
      cat("Date range:", min(nse_index_data$TIMESTAMP), "to", max(nse_index_data$TIMESTAMP), "\n")
      
      return(nse_index_data)
    } else {
      stop("No NSE index data retrieved")
    }
    
  }, error = function(e) {
    warning("Failed to load NSE index data:", e$message)
    
    # Try to load cached data as fallback
    if(file.exists(cache_file)) {
      load(cache_file)
      if(exists("nse_index_data")) {
        warning("Using cached NSE index data as fallback")
        return(nse_index_data)
      }
    }
    
    return(data.frame())
  })
}

#' Load NSE stock data with caching
#' @param config Project configuration list
#' @param symbols Vector of stock symbols to load (optional)
#' @param force_refresh Boolean to force data refresh
#' @return Data frame with NSE stock data
load_nse_stock_data <- function(config = PROJECT_CONFIG, symbols = NULL, force_refresh = FALSE) {
  
  cache_file <- file.path(config$paths$dirs$data, "nse_stock_cache.RData")
  
  # Check if cached data exists and is recent
  if(!force_refresh && file.exists(cache_file)) {
    load(cache_file)
    
    if(exists("nse_stock_data") && nrow(nse_stock_data) > 0) {
      latest_date <- max(as.Date(nse_stock_data$TIMESTAMP), na.rm = TRUE)
      
      if(Sys.Date() - latest_date <= 1) {
        cat("Loading NSE stock data from cache (latest:", as.character(latest_date), ")\n")
        
        # Filter by symbols if specified
        if(!is.null(symbols)) {
          nse_stock_data <- nse_stock_data[nse_stock_data$SYMBOL %in% symbols, ]
        }
        
        return(nse_stock_data)
      }
    }
  }
  
  cat("Loading fresh NSE stock data...\n")
  
  tryCatch({
    # Load the helpers.R file which contains data loading functions
    source(file.path(config$paths$legacy_data, "helpers.R"))
    
    # Load stock data from the available CSV file
    # The helpers.R file has commented out dt.NSE.GLOBAL loading
    # Let's load it directly from the CSV file
    stock_data_file <- file.path(config$paths$legacy_data, "nse_sec_full_data.csv")
    
    if(file.exists(stock_data_file)) {
      nse_stock_data <- read.csv(stock_data_file, stringsAsFactors = FALSE)
      cat("Loaded stock data from:", stock_data_file, "\n")
    } else {
      # Fallback to empty data frame
      nse_stock_data <- data.frame(
        SYMBOL = character(0),
        TIMESTAMP = character(0),
        OPEN = numeric(0),
        HIGH = numeric(0),
        LOW = numeric(0),
        CLOSE = numeric(0),
        TOTTRDQTY = numeric(0),
        stringsAsFactors = FALSE
      )
    }
    
    # Cache the data
    save(nse_stock_data, file = cache_file)
    cat("NSE stock data loaded and cached:", nrow(nse_stock_data), "records\n")
    
    return(nse_stock_data)
    
  }, error = function(e) {
    warning("Failed to load NSE stock data:", e$message)
    
    # Try to load cached data as fallback
    if(file.exists(cache_file)) {
      load(cache_file)
      if(exists("nse_stock_data")) {
        warning("Using cached NSE stock data as fallback")
        
        # Filter by symbols if specified
        if(!is.null(symbols)) {
          nse_stock_data <- nse_stock_data[nse_stock_data$SYMBOL %in% symbols, ]
        }
        
        return(nse_stock_data)
      }
    }
    
    return(data.frame())
  })
}

#' Load NSE symbol master data
#' @param config Project configuration list
#' @param analysis_type Type of analysis ("index" or "stock")
#' @return Data frame with symbol information
load_symbol_master <- function(config = PROJECT_CONFIG, analysis_type = "index") {
  
  if(analysis_type == "index") {
    # Load index symbols from the indices data file
    index_file <- file.path(config$paths$legacy_data, "nse_indices_data_all.csv")
    
    if(file.exists(index_file)) {
      symbol_data <- read.csv(index_file, stringsAsFactors = FALSE)
      # Get unique indices
      unique_indices <- unique(symbol_data$Index)
      index_symbols <- data.frame(
        SYMBOL = unique_indices,
        stringsAsFactors = FALSE
      )
      cat("Loaded", nrow(index_symbols), "unique index symbols\n")
      return(index_symbols)
    } else {
      warning("Index symbol file not found:", index_file)
      return(data.frame())
    }
    
  } else if(analysis_type == "stock") {
    # Load stock symbols from the indices data file
    stock_file <- file.path(config$paths$legacy_data, "nse_indices_data_all.csv")
    
    if(file.exists(stock_file)) {
      symbol_data <- read.csv(stock_file, stringsAsFactors = FALSE)
      # Get unique stock symbols
      stock_symbols <- data.frame(
        SYMBOL = unique(symbol_data$Symbol),
        stringsAsFactors = FALSE
      )
      cat("Loaded", nrow(stock_symbols), "unique stock symbols\n")
      return(stock_symbols)
    } else {
      warning("Stock symbol file not found:", stock_file)
      return(data.frame())
    }
    
  } else {
    stop("Invalid analysis_type. Must be 'index' or 'stock'")
  }
}

#' Preprocess and clean NSE data
#' @param raw_data Raw NSE data frame
#' @param analysis_type Type of analysis ("index" or "stock")
#' @param config Analysis configuration
#' @return Cleaned and preprocessed data frame
preprocess_nse_data <- function(raw_data, analysis_type = "index", config = ANALYSIS_CONFIG) {
  
  if(nrow(raw_data) == 0) {
    warning("No data to preprocess")
    return(raw_data)
  }
  
  cat("Preprocessing", nrow(raw_data), "records...\n")
  
  # Convert timestamps to Date
  if("TIMESTAMP" %in% names(raw_data)) {
    raw_data$TIMESTAMP <- as.Date(raw_data$TIMESTAMP)
  }
  
  # Remove records with missing essential data
  essential_cols <- c("OPEN", "HIGH", "LOW", "CLOSE")
  complete_rows <- complete.cases(raw_data[, essential_cols])
  clean_data <- raw_data[complete_rows, ]
  
  if(nrow(clean_data) < nrow(raw_data)) {
    cat("Removed", nrow(raw_data) - nrow(clean_data), "incomplete records\n")
  }
  
  # Validate price data integrity
  invalid_prices <- with(clean_data, {
    HIGH < LOW | CLOSE < 0 | OPEN < 0 | HIGH < 0 | LOW < 0
  })
  
  if(any(invalid_prices, na.rm = TRUE)) {
    clean_data <- clean_data[!invalid_prices, ]
    cat("Removed", sum(invalid_prices, na.rm = TRUE), "records with invalid prices\n")
  }
  
  # Handle volume data
  if("TOTTRDQTY" %in% names(clean_data)) {
    # Convert to numeric if needed
    clean_data$TOTTRDQTY <- as.numeric(clean_data$TOTTRDQTY)
    clean_data$TOTTRDQTY[is.na(clean_data$TOTTRDQTY)] <- 0
    
    # For indices, volume might not be meaningful
    if(analysis_type == "index" && mean(clean_data$TOTTRDQTY, na.rm = TRUE) == 0) {
      cat("Volume data appears to be zero for index data (expected)\n")
    }
  }
  
  # Sort by symbol and timestamp
  if("SYMBOL" %in% names(clean_data) && "TIMESTAMP" %in% names(clean_data)) {
    clean_data <- clean_data[order(clean_data$SYMBOL, clean_data$TIMESTAMP), ]
  }
  
  cat("Preprocessing complete:", nrow(clean_data), "clean records\n")
  return(clean_data)
}

#' Get latest data for all symbols
#' @param historical_data Complete historical data
#' @param config Analysis configuration
#' @return Data frame with latest data for each symbol
get_latest_data_by_symbol <- function(historical_data, config = ANALYSIS_CONFIG) {
  
  if(nrow(historical_data) == 0) {
    return(data.frame())
  }
  
  # Group by symbol and get latest date for each
  latest_data <- historical_data %>%
    group_by(SYMBOL) %>%
    filter(TIMESTAMP == max(TIMESTAMP, na.rm = TRUE)) %>%
    ungroup()
  
  cat("Latest data retrieved for", nrow(latest_data), "symbols\n")
  return(as.data.frame(latest_data))
}

#' Validate data quality and completeness
#' @param data_frame Data frame to validate
#' @param analysis_type Type of analysis for validation rules
#' @return List with validation results
validate_data_quality <- function(data_frame, analysis_type = "index") {
  
  validation_results <- list(
    is_valid = TRUE,
    warnings = character(0),
    errors = character(0),
    summary = list()
  )
  
  # Check basic structure
  if(nrow(data_frame) == 0) {
    validation_results$errors <- c(validation_results$errors, "Data frame is empty")
    validation_results$is_valid <- FALSE
    return(validation_results)
  }
  
  # Check required columns
  required_cols <- c("SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE")
  missing_cols <- required_cols[!required_cols %in% names(data_frame)]
  
  if(length(missing_cols) > 0) {
    validation_results$errors <- c(validation_results$errors, 
                                 paste("Missing required columns:", paste(missing_cols, collapse = ", ")))
    validation_results$is_valid <- FALSE
  }
  
  # Data quality checks
  if(validation_results$is_valid) {
    # Check for duplicate records
    if("SYMBOL" %in% names(data_frame) && "TIMESTAMP" %in% names(data_frame)) {
      duplicates <- duplicated(data_frame[, c("SYMBOL", "TIMESTAMP")])
      if(any(duplicates)) {
        validation_results$warnings <- c(validation_results$warnings, 
                                       paste("Found", sum(duplicates), "duplicate records"))
      }
    }
    
    # Check data freshness
    if("TIMESTAMP" %in% names(data_frame)) {
      latest_date <- max(as.Date(data_frame$TIMESTAMP), na.rm = TRUE)
      days_old <- as.numeric(Sys.Date() - latest_date)
      
      if(days_old > 7) {
        validation_results$warnings <- c(validation_results$warnings, 
                                       paste("Data may be stale - latest date is", days_old, "days old"))
      }
      
      validation_results$summary$latest_date <- latest_date
      validation_results$summary$days_old <- days_old
    }
    
    # Summary statistics
    validation_results$summary$total_records <- nrow(data_frame)
    validation_results$summary$unique_symbols <- length(unique(data_frame$SYMBOL))
    validation_results$summary$date_range <- if("TIMESTAMP" %in% names(data_frame)) {
      c(min(data_frame$TIMESTAMP), max(data_frame$TIMESTAMP))
    } else {
      NULL
    }
  }
  
  return(validation_results)
}

#' Clear data cache files
#' @param config Project configuration list
#' @param cache_type Type of cache to clear ("all", "index", "stock")
clear_data_cache <- function(config = PROJECT_CONFIG, cache_type = "all") {
  
  cache_files <- list()
  
  if(cache_type %in% c("all", "index")) {
    cache_files[["index"]] <- file.path(config$paths$data_dir, "nse_index_cache.RData")
  }
  
  if(cache_type %in% c("all", "stock")) {
    cache_files[["stock"]] <- file.path(config$paths$data_dir, "nse_stock_cache.RData")
  }
  
  cleared_count <- 0
  
  for(cache_name in names(cache_files)) {
    cache_file <- cache_files[[cache_name]]
    
    if(file.exists(cache_file)) {
      file.remove(cache_file)
      cat("Cleared", cache_name, "cache\n")
      cleared_count <- cleared_count + 1
    }
  }
  
  if(cleared_count == 0) {
    cat("No cache files found to clear\n")
  } else {
    cat("Cleared", cleared_count, "cache files\n")
  }
}
