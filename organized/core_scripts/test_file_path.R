# Test file path issue
cat("Current working directory:", getwd(), "\n")

# Test different paths
paths_to_test <- c(
  "organized/backtesting_results",
  "../backtesting_results", 
  "backtesting_results",
  "./organized/backtesting_results"
)

for(path in paths_to_test) {
  cat("\nTesting path:", path, "\n")
  if(dir.exists(path)) {
    cat("✓ Directory exists\n")
    files <- list.files(path, pattern = "real_backtesting_performance_.*\\.csv")
    cat("Files found:", length(files), "\n")
    if(length(files) > 0) {
      cat("Sample files:", head(files, 3), "\n")
    }
  } else {
    cat("✗ Directory does not exist\n")
  }
}






