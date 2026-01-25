# ================================================================================
# UNIFIED LIBRARY MANAGER
# ================================================================================
# Purpose: Centralized library loading and management for NSE analysis
# ================================================================================

#' Load all required libraries for NSE analysis
#' @param verbose Boolean indicating whether to show loading messages
load_required_libraries <- function(verbose = TRUE) {
  
  if(verbose) cat("Loading required libraries...\n")
  
  # Define required libraries in logical groups
  required_libs <- list(
    # Core data manipulation
    data = c('dplyr', 'readr', 'tibble', 'data.table'),
    
    # String and factor manipulation  
    text = c('stringr', 'forcats'),
    
    # Date/time handling
    datetime = c('lubridate'),
    
    # Financial and time series analysis
    financial = c('TTR', 'quantmod', 'tidyquant', 'forecast'),
    
    # Technical analysis and modeling
    technical = c('rugarch', 'MLmetrics'),
    
    # Machine learning
    ml = c('caret', 'xgboost', 'randomForest', 'mlr'),
    
    # Statistics and modeling
    stats = c('VIM', 'vcd', 'pROC'),
    
    # Database and SQL
    database = c('sqldf'),
    
    # Parallel processing
    parallel = c('parallel', 'doParallel', 'foreach'),
    
    # Visualization (optional)
    viz = c('ggplot2'),
    
    # Utilities
    utils = c('purrr', 'httr')
  )
  
  # Function to safely load a library
  safe_load <- function(lib_name) {
    tryCatch({
      if (!require(lib_name, character.only = TRUE, quietly = !verbose)) {
        if(verbose) cat("Installing missing package:", lib_name, "\n")
        install.packages(lib_name, dependencies = TRUE)
        library(lib_name, character.only = TRUE)
      }
      return(TRUE)
    }, error = function(e) {
      warning(paste("Failed to load library:", lib_name, "-", e$message))
      return(FALSE)
    })
  }
  
  # Load libraries by category
  loaded_libs <- c()
  failed_libs <- c()
  
  for(category in names(required_libs)) {
    if(verbose) cat("Loading", category, "libraries...\n")
    
    for(lib in required_libs[[category]]) {
      if(safe_load(lib)) {
        loaded_libs <- c(loaded_libs, lib)
      } else {
        failed_libs <- c(failed_libs, lib)
      }
    }
  }
  
  # Special handling for Matrix (required by some packages)
  if(!require(Matrix, quietly = TRUE)) {
    install.packages("Matrix")
    library(Matrix)
  }
  
  # Report results
  if(verbose) {
    cat("\n=== LIBRARY LOADING SUMMARY ===\n")
    cat("Successfully loaded:", length(loaded_libs), "libraries\n")
    if(length(failed_libs) > 0) {
      cat("Failed to load:", length(failed_libs), "libraries:", paste(failed_libs, collapse = ", "), "\n")
    }
    cat("===============================\n")
  }
  
  # Handle conflicting functions
  handle_conflicts()
  
  return(list(
    loaded = loaded_libs,
    failed = failed_libs,
    success = length(failed_libs) == 0
  ))
}

#' Handle conflicting functions between packages
handle_conflicts <- function() {
  
  # Resolve common conflicts
  if(exists("filter", envir = .GlobalEnv)) {
    # Prefer dplyr::filter over stats::filter
    filter <- dplyr::filter
  }
  
  if(exists("lag", envir = .GlobalEnv)) {
    # Prefer dplyr::lag over stats::lag for most cases
    lag <- dplyr::lag
  }
  
  # Handle xts/zoo conflicts with lubridate
  options(xts.warn_dplyr_breaks_lag = FALSE)
  
  # Suppress specific warnings
  suppressMessages({
    if("conflicted" %in% rownames(installed.packages())) {
      library(conflicted)
      conflict_prefer("filter", "dplyr")
      conflict_prefer("lag", "dplyr")
      conflict_prefer("first", "dplyr")
      conflict_prefer("last", "dplyr")
    }
  })
}

#' Check if all required libraries are available
#' @return Boolean indicating if all libraries are loaded
check_libraries <- function() {
  
  essential_libs <- c("dplyr", "TTR", "lubridate", "forecast", "parallel")
  
  missing <- c()
  for(lib in essential_libs) {
    if(!lib %in% loadedNamespaces()) {
      missing <- c(missing, lib)
    }
  }
  
  if(length(missing) > 0) {
    cat("Missing essential libraries:", paste(missing, collapse = ", "), "\n")
    return(FALSE)
  }
  
  return(TRUE)
}

#' Get library information and versions
get_library_info <- function() {
  
  loaded_packages <- loadedNamespaces()
  
  package_info <- data.frame(
    Package = loaded_packages,
    Version = sapply(loaded_packages, function(x) {
      tryCatch(as.character(packageVersion(x)), error = function(e) "Unknown")
    }),
    stringsAsFactors = FALSE
  )
  
  return(package_info)
}

# Auto-load libraries when this file is sourced
if(!exists("LIBRARIES_LOADED")) {
  load_result <- load_required_libraries(verbose = TRUE)
  LIBRARIES_LOADED <- load_result$success
  
  if(!LIBRARIES_LOADED) {
    warning("Some libraries failed to load. Check the output above.")
  }
}
