# ================================================================================
# UNIFIED NSE ANALYSIS - MAIN ENTRY POINT
# ================================================================================
# Purpose: Main script to run the unified NSE analysis system
# Usage: source("main.R") or Rscript main.R
# ================================================================================

# Clear workspace and set working directory
rm(list = ls())

# Set working directory to script location
tryCatch({
  # Try to get script path
  if (exists("rstudioapi") && rstudioapi::isAvailable()) {
    script_path <- dirname(rstudioapi::getActiveDocumentContext()$path)
    setwd(script_path)
  } else {
    # For command line execution, use current working directory
    script_path <- getwd()
    if (basename(script_path) != "Unified-NSE-Analysis") {
      # If not already in the right directory, try to find it
      if (file.exists("Unified-NSE-Analysis")) {
        setwd("Unified-NSE-Analysis")
      }
    }
  }
}, error = function(e) {
  # Fallback: just use current directory
  cat("Using current working directory:", getwd(), "
")
})

cat("\n", paste(rep("=", 80), collapse=""), "\n")
cat("UNIFIED NSE ANALYSIS SYSTEM\n")
cat(paste(rep("=", 80), collapse=""), "\n")
cat("Initializing system...\n\n")

# ================================================================================
# 1. LOAD CONFIGURATION AND LIBRARIES
# ================================================================================

# Load project configuration
source("config.R")

# Export configuration to global environment for access by other functions
if (exists("PROJECT_CONFIG")) {
  assign("PROJECT_CONFIG", PROJECT_CONFIG, envir = .GlobalEnv)
}

# Load and install required libraries
source("core/library_manager.R")
load_required_libraries()

# Source helper functions from legacy scripts if needed
tryCatch({
  source(file.path(PROJECT_ROOT, "helpers.R"))
  source(file.path(PROJECT_ROOT, "FOhelpers.R"))
  cat("✓ Helper functions loaded\n")
}, error = function(e) {
  warning("Could not load helper functions:", e$message)
})

# ================================================================================
# 2. LOAD CORE MODULES
# ================================================================================

cat("Loading core modules...\n")

# Load data management functions
source("core/data_manager.R")
cat("✓ Data manager loaded\n")

# Load technical analysis engine
source("core/technical_analysis_engine.R")
cat("✓ Technical analysis engine loaded\n")

# Load analysis pipeline
source("core/analysis_pipeline.R")
cat("✓ Analysis pipeline loaded\n")

cat("✓ All core modules loaded successfully\n\n")

# ================================================================================
# 3. MAIN EXECUTION FUNCTION
# ================================================================================

#' Main execution function with command line argument support
#' @param args Command line arguments
run_main_analysis <- function(args = commandArgs(trailingOnly = TRUE)) {
  
  # Default parameters
  analysis_type <- "index"
  force_refresh <- FALSE
  output_results <- TRUE
  interactive_mode <- length(args) == 0
  
  # Parse command line arguments
  if(length(args) > 0) {
    for(i in 1:length(args)) {
      arg <- args[i]
      
      if(arg %in% c("--type", "-t") && i < length(args)) {
        analysis_type <- args[i + 1]
      } else if(arg %in% c("--refresh", "-r")) {
        force_refresh <- TRUE
      } else if(arg %in% c("--no-output", "-n")) {
        output_results <- FALSE
      } else if(arg %in% c("--help", "-h")) {
        print_usage()
        return(invisible(NULL))
      }
    }
  }
  
  # Interactive mode - ask user for preferences
  if(interactive_mode) {
    cat("INTERACTIVE MODE\n")
    cat(paste(rep("-", 40), collapse=""), "\n")
    
    # Ask for analysis type
    cat("Select analysis type:\n")
    cat("  1. Index analysis only\n")
    cat("  2. Stock analysis only\n") 
    cat("  3. Both index and stock analysis\n")
    
    choice <- readline("Enter choice (1-3) [default: 1]: ")
    
    analysis_type <- switch(choice,
      "1" = "index",
      "2" = "stock", 
      "3" = "both",
      "index"  # default
    )
    
    # Ask about data refresh
    refresh_choice <- readline("Force data refresh? (y/N): ")
    force_refresh <- tolower(substr(refresh_choice, 1, 1)) == "y"
    
    cat("\n")
  }
  
  # Validate analysis type
  if(!analysis_type %in% c("index", "stock", "both")) {
    stop("Invalid analysis type. Must be one of: index, stock, both")
  }
  
  cat("EXECUTION PARAMETERS\n")
  cat(paste(rep("-", 40), collapse=""), "\n")
  cat("Analysis Type:", analysis_type, "\n")
  cat("Force Refresh:", force_refresh, "\n")
  cat("Generate Output:", output_results, "\n")
  cat("Interactive Mode:", interactive_mode, "\n\n")
  
  # ================================================================================
  # 4. RUN ANALYSIS PIPELINE
  # ================================================================================
  
  # Execute the main analysis pipeline
  results <- run_nse_analysis_pipeline(
    analysis_type = analysis_type,
    force_refresh = force_refresh,
    output_results = output_results,
    config = list(
      project = PROJECT_CONFIG,
      analysis = ANALYSIS_CONFIG,
      output = OUTPUT_CONFIG
    )
  )
  
  # ================================================================================
  # 5. POST-PROCESSING AND CLEANUP
  # ================================================================================
  
  if(results$success) {
    cat("\n✅ ANALYSIS COMPLETED SUCCESSFULLY\n")
    
    # Display quick summary
    if(!is.null(results$index_results) && results$index_results$success) {
      cat("📊 Index Analysis: Processed", nrow(results$index_results$technical_results), "symbols\n")
    }
    
    if(!is.null(results$stock_results) && results$stock_results$success) {
      cat("📈 Stock Analysis: Processed", nrow(results$stock_results$technical_results), "symbols\n")
    }
    
    cat("⏱️  Total Execution Time:", format(results$execution_time), "\n")
    
    if(output_results) {
      cat("📁 Output files saved to:", OUTPUT_CONFIG$output_dir, "\n")
    }
    
  } else {
    cat("\n❌ ANALYSIS FAILED\n")
    
    if(length(results$errors) > 0) {
      cat("Errors encountered:\n")
      for(error in results$errors) {
        cat("  •", error, "\n")
      }
    }
    
    cat("\nPlease check the error messages above and try again.\n")
  }
  
  # Save results for potential inspection
  save(results, file = file.path(OUTPUT_CONFIG$output_dir, "last_analysis_results.RData"))
  
  cat("\n", paste(rep("=", 80), collapse=""), "\n")
  
  return(invisible(results))
}

#' Print usage information
print_usage <- function() {
  cat("UNIFIED NSE ANALYSIS SYSTEM - USAGE\n")
  cat(paste(rep("=", 50), collapse=""), "\n")
  cat("Command line usage:\n")
  cat("  Rscript main.R [options]\n\n")
  cat("Options:\n")
  cat("  --type, -t TYPE     Analysis type: index, stock, or both [default: index]\n")
  cat("  --refresh, -r       Force data refresh from sources\n")
  cat("  --no-output, -n     Skip generating output files\n")
  cat("  --help, -h          Show this help message\n\n")
  cat("Interactive usage:\n")
  cat("  source(\"main.R\")\n")
  cat("  run_main_analysis()  # Will prompt for options\n\n")
  cat("Examples:\n")
  cat("  Rscript main.R                    # Interactive mode\n")
  cat("  Rscript main.R -t both -r         # Both analyses with data refresh\n")
  cat("  Rscript main.R -t index -n        # Index analysis without output files\n")
}

# ================================================================================
# 6. AUTO-EXECUTION
# ================================================================================

# If script is being executed directly (not sourced), run the analysis
if(sys.nframe() == 0) {
  tryCatch({
    run_main_analysis()
  }, error = function(e) {
    cat("\n❌ FATAL ERROR:\n")
    cat("Error:", e$message, "\n")
    cat("Please check your configuration and try again.\n")
    cat(paste(rep("=", 80), collapse=""), "\n")
    quit(status = 1)
  })
}

# ================================================================================
# 7. ADDITIONAL UTILITY FUNCTIONS
# ================================================================================

#' Quick analysis function for development/testing
#' @param type Analysis type ("index" or "stock")
#' @param refresh Force refresh boolean
quick_analysis <- function(type = "index", refresh = FALSE) {
  cat("Running quick", type, "analysis...\n")
  
  results <- run_nse_analysis_pipeline(
    analysis_type = type,
    force_refresh = refresh,
    output_results = FALSE
  )
  
  if(results$success) {
    cat("✓ Quick analysis completed\n")
    return(results)
  } else {
    cat("✗ Quick analysis failed\n")
    return(NULL)
  }
}

#' Clear all data caches
clear_all_caches <- function() {
  cat("Clearing all data caches...\n")
  clear_data_cache(PROJECT_CONFIG, "all")
  cat("✓ All caches cleared\n")
}

#' System status check
check_system_status <- function() {
  cat("SYSTEM STATUS CHECK\n")
  cat(paste(rep("=", 30), collapse=""), "\n")
  
  # Check configuration
  cat("Configuration: ")
  if(exists("PROJECT_CONFIG") && exists("ANALYSIS_CONFIG") && exists("OUTPUT_CONFIG")) {
    cat("✓ Loaded\n")
  } else {
    cat("✗ Missing\n")
  }
  
  # Check core modules
  cat("Core Modules: ")
  required_functions <- c("load_nse_index_data", "calculate_technical_indicators", "run_nse_analysis_pipeline")
  
  if(all(sapply(required_functions, exists))) {
    cat("✓ Loaded\n")
  } else {
    cat("✗ Missing functions\n")
  }
  
  # Check data directories
  cat("Data Directories: ")
  if(dir.exists(PROJECT_CONFIG$paths$data_dir) && dir.exists(OUTPUT_CONFIG$output_dir)) {
    cat("✓ Available\n")
  } else {
    cat("✗ Missing directories\n")
  }
  
  # Check for recent data
  cache_file <- file.path(PROJECT_CONFIG$paths$data_dir, "nse_index_cache.RData")
  cat("Data Cache: ")
  if(file.exists(cache_file)) {
    file_age <- Sys.Date() - as.Date(file.info(cache_file)$mtime)
    cat("✓ Available (", as.numeric(file_age), "days old)\n")
  } else {
    cat("✗ Not found\n")
  }
  
  cat(paste(rep("=", 30), collapse=""), "\n")
}

cat("✅ Unified NSE Analysis System ready!\n")
cat("Type 'run_main_analysis()' to start, or 'check_system_status()' to verify setup.\n")
cat(paste(rep("=", 80), collapse=""), "\n\n")
