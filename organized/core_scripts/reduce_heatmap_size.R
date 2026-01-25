#!/usr/bin/env Rscript

# =============================================================================
# Reduce Heat Map Card Sizes in HTML Dashboard
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(stringr)
  library(readr)
})

cat("Reducing heat map card sizes in HTML dashboard...\n")

# Read the HTML file
html_file <- "../../reports/NSE_Interactive_Dashboard_with_Sorting.html"
html_content <- readLines(html_file, warn = FALSE)

# Find the heat map cell CSS styles
heatmap_cell_pattern <- "\\.heatmap-cell \\{"
heatmap_cell_start <- which(str_detect(html_content, heatmap_cell_pattern))

if(length(heatmap_cell_start) == 0) {
  stop("Could not find heat map cell styles in HTML file")
}

# Find the end of the heatmap-cell CSS block
heatmap_cell_end <- heatmap_cell_start
for(i in (heatmap_cell_start + 1):length(html_content)) {
  if(str_detect(html_content[i], "^\\s*\\}")) {
    heatmap_cell_end <- i
    break
  }
}

# Create new smaller heat map cell styles
new_heatmap_cell_css <- c(
  "        .heatmap-cell {",
  "            aspect-ratio: 1;",
  "            display: flex;",
  "            align-items: center;",
  "            justify-content: center;",
  "            font-size: 0.6rem;",
  "            font-weight: 600;",
  "            color: white;",
  "            border-radius: 6px;",
  "            cursor: pointer;",
  "            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);",
  "            min-width: 32px;",
  "            min-height: 32px;",
  "            box-shadow: 0 2px 6px rgba(0,0,0,0.1);",
  "        }"
)

# Replace the heat map cell styles
html_content <- c(
  html_content[1:(heatmap_cell_start - 1)],
  new_heatmap_cell_css,
  html_content[(heatmap_cell_end + 1):length(html_content)]
)

# Also update the responsive styles for mobile
mobile_pattern <- "@media \\(max-width: 768px\\) \\{"
mobile_start <- which(str_detect(html_content, mobile_pattern))

if(length(mobile_start) > 0) {
  # Find the mobile heat map styles
  mobile_heatmap_pattern <- "\\.heatmap-cell \\{"
  mobile_heatmap_start <- which(str_detect(html_content, mobile_heatmap_pattern))
  mobile_heatmap_start <- mobile_heatmap_start[mobile_heatmap_start > mobile_start][1]
  
  if(!is.na(mobile_heatmap_start)) {
    # Find the end of mobile heat map styles
    mobile_heatmap_end <- mobile_heatmap_start
    for(i in (mobile_heatmap_start + 1):length(html_content)) {
      if(str_detect(html_content[i], "^\\s*\\}")) {
        mobile_heatmap_end <- i
        break
      }
    }
    
    # Create new smaller mobile heat map styles
    new_mobile_heatmap_css <- c(
      "            .heatmap-cell {",
      "                min-width: 26px;",
      "                min-height: 26px;",
      "                font-size: 0.5rem;",
      "            }"
    )
    
    # Replace the mobile heat map styles
    html_content <- c(
      html_content[1:(mobile_heatmap_start - 1)],
      new_mobile_heatmap_css,
      html_content[(mobile_heatmap_end + 1):length(html_content)]
    )
  }
}

# Update the 480px mobile styles as well
mobile_480_pattern <- "@media \\(max-width: 480px\\) \\{"
mobile_480_start <- which(str_detect(html_content, mobile_480_pattern))

if(length(mobile_480_start) > 0) {
  # Find the mobile 480px heat map styles
  mobile_480_heatmap_pattern <- "\\.heatmap-cell \\{"
  mobile_480_heatmap_start <- which(str_detect(html_content, mobile_480_heatmap_pattern))
  mobile_480_heatmap_start <- mobile_480_heatmap_start[mobile_480_heatmap_start > mobile_480_start][1]
  
  if(!is.na(mobile_480_heatmap_start)) {
    # Find the end of mobile 480px heat map styles
    mobile_480_heatmap_end <- mobile_480_heatmap_start
    for(i in (mobile_480_heatmap_start + 1):length(html_content)) {
      if(str_detect(html_content[i], "^\\s*\\}")) {
        mobile_480_heatmap_end <- i
        break
      }
    }
    
    # Create new smaller mobile 480px heat map styles
    new_mobile_480_heatmap_css <- c(
      "            .heatmap-cell {",
      "                min-width: 22px;",
      "                min-height: 22px;",
      "                font-size: 0.4rem;",
      "            }"
    )
    
    # Replace the mobile 480px heat map styles
    html_content <- c(
      html_content[1:(mobile_480_heatmap_start - 1)],
      new_mobile_480_heatmap_css,
      html_content[(mobile_480_heatmap_end + 1):length(html_content)]
    )
  }
}

# Write the updated HTML file
writeLines(html_content, html_file)

cat("✅ Successfully reduced heat map card sizes!\n")
cat("📁 Updated file:", html_file, "\n")
cat("🎯 Changes made:\n")
cat("   - Desktop: min-width/min-height reduced to 32px (from 40px)\n")
cat("   - Tablet (768px): min-width/min-height reduced to 26px (from 30px)\n")
cat("   - Mobile (480px): min-width/min-height reduced to 22px (from 25px)\n")
cat("   - Font sizes also reduced proportionally\n")






