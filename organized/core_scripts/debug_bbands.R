# =============================================================================
# DEBUG BOLLINGER BANDS - UNDERSTAND THE STRUCTURE
# =============================================================================

library(TTR)

# Create sample data
prices <- c(100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110)

cat("Sample prices:", prices, "\n")
cat("Length:", length(prices), "\n")

# Test BBands
bb_result <- BBands(prices, n = 5, sd = 2)

cat("\nBBands result:\n")
print(bb_result)
cat("\nDimensions:", dim(bb_result), "\n")
cat("Column names:", colnames(bb_result), "\n")

# Test accessing each column
cat("\nTesting column access:\n")
cat("Upper:", bb_result[1, "upper"], "\n")
cat("Middle:", bb_result[1, "middle"], "\n")
cat("Lower:", bb_result[1, "lower"], "\n")

# Check if there's a 4th column
if(ncol(bb_result) >= 4) {
  cat("4th column name:", colnames(bb_result)[4], "\n")
  cat("4th column value:", bb_result[1, 4], "\n")
}






