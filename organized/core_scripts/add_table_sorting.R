#!/usr/bin/env Rscript

# =============================================================================
# Add Table Sorting to HTML Dashboard
# =============================================================================

# Load required libraries
suppressPackageStartupMessages({
  library(stringr)
  library(readr)
})

cat("Adding table sorting functionality to HTML dashboard...\n")

# Find the latest HTML dashboard file (exclude the _with_Sorting version)
html_files <- list.files("../../reports/", pattern = "NSE_Interactive_Dashboard_.*\\.html", full.names = TRUE)
html_files <- html_files[!grepl("_with_Sorting", html_files)]
if(length(html_files) == 0) {
  stop("No HTML dashboard files found")
}
html_file <- html_files[order(file.info(html_files)$mtime, decreasing = TRUE)[1]]
cat("Using HTML file:", basename(html_file), "\n")
html_content <- readLines(html_file, warn = FALSE)

# Find the table headers section
table_start <- which(str_detect(html_content, "<thead>"))
table_end <- which(str_detect(html_content, "</thead>"))

if(length(table_start) == 0 || length(table_end) == 0) {
  stop("Could not find table structure in HTML file")
}

# Add sorting CSS styles
sorting_css <- c(
  "",
  "        /* Sorting styles */",
  "        .stocks-table th {",
  "            cursor: pointer;",
  "            position: relative;",
  "            user-select: none;",
  "        }",
  "        .stocks-table th:hover {",
  "            background-color: rgba(255, 255, 255, 0.1);",
  "        }",
  "        .stocks-table th.sortable::after {",
  "            content: '↕';",
  "            position: absolute;",
  "            right: 8px;",
  "            color: rgba(255, 255, 255, 0.6);",
  "            font-size: 12px;",
  "        }",
  "        .stocks-table th.sort-asc::after {",
  "            content: '↑';",
  "            color: #4CAF50;",
  "        }",
  "        .stocks-table th.sort-desc::after {",
  "            content: '↓';",
  "            color: #f44336;",
  "        }",
  ""
)

# Find where to insert CSS (after existing table styles)
css_insert_pos <- which(str_detect(html_content, "\\.stocks-table td \\{"))[1] + 10

# Insert the CSS
html_content <- c(
  html_content[1:css_insert_pos],
  sorting_css,
  html_content[(css_insert_pos + 1):length(html_content)]
)

# Update table headers to be clickable
header_line <- which(str_detect(html_content, "<th>Rank</th>"))[1]
if(!is.na(header_line)) {
  # Replace the header row with clickable headers
  new_headers <- c(
    "                    <tr>",
    "                        <th class=\"sortable\" data-sort=\"rank\">Rank</th>",
    "                        <th class=\"sortable\" data-sort=\"symbol\">Stock</th>",
    "                        <th class=\"sortable\" data-sort=\"companyName\">Company Name</th>",
    "                        <th class=\"sortable\" data-sort=\"marketCap\">Market Cap</th>",
    "                        <th class=\"sortable\" data-sort=\"currentPrice\">Price</th>",
    "                        <th class=\"sortable\" data-sort=\"change1D\">1D</th>",
    "                        <th class=\"sortable\" data-sort=\"change1W\">1W</th>",
    "                        <th class=\"sortable\" data-sort=\"change1M\">1M</th>",
    "                        <th class=\"sortable\" data-sort=\"technicalScore\">Tech Score</th>",
    "                        <th class=\"sortable\" data-sort=\"rsi\">RSI</th>",
    "                        <th class=\"sortable\" data-sort=\"relativeStrength\">RS</th>",
    "                        <th class=\"sortable\" data-sort=\"canSlim\">CAN SLIM</th>",
    "                        <th class=\"sortable\" data-sort=\"minervini\">Minervini</th>",
    "                        <th class=\"sortable\" data-sort=\"fundamental\">Fundamental</th>",
    "                        <th class=\"sortable\" data-sort=\"trendSignal\">Trend</th>",
    "                        <th class=\"sortable\" data-sort=\"tradingSignal\">Signal</th>",
    "                    </tr>"
  )
  
  # Find the end of the header row
  header_end <- which(str_detect(html_content, "</tr>"))[which(str_detect(html_content, "</tr>")) > header_line][1]
  
  # Replace the header section
  html_content <- c(
    html_content[1:(header_line - 1)],
    new_headers,
    html_content[(header_end + 1):length(html_content)]
  )
}

# Find where to insert JavaScript sorting functions
js_insert_pos <- which(str_detect(html_content, "// Stock data from analysis"))[1] - 1

# Add sorting JavaScript functions
sorting_js <- c(
  "",
  "        // Sorting functionality",
  "        let currentSort = { column: 'rank', direction: 'asc' };",
  "",
  "        // Add click event listeners to table headers",
  "        document.addEventListener('DOMContentLoaded', function() {",
  "            const headers = document.querySelectorAll('.stocks-table th.sortable');",
  "            headers.forEach(header => {",
  "                header.addEventListener('click', function() {",
  "                    const column = this.getAttribute('data-sort');",
  "                    sortTable(column);",
  "                });",
  "            });",
  "        });",
  "",
  "        function sortTable(column) {",
  "            const tbody = document.getElementById('stocksTableBody');",
  "            const rows = Array.from(tbody.querySelectorAll('tr'));",
  "            const headers = document.querySelectorAll('.stocks-table th.sortable');",
  "",
  "            // Clear previous sort indicators",
  "            headers.forEach(h => {",
  "                h.classList.remove('sort-asc', 'sort-desc');",
  "            });",
  "",
  "            // Determine sort direction",
  "            let direction = 'asc';",
  "            if (currentSort.column === column && currentSort.direction === 'asc') {",
  "                direction = 'desc';",
  "            }",
  "",
  "            // Update sort indicator",
  "            const header = document.querySelector(`[data-sort=\"${column}\"]`);",
  "            header.classList.add(direction === 'asc' ? 'sort-asc' : 'sort-desc');",
  "",
  "            // Sort the rows",
  "            rows.sort((a, b) => {",
  "                let aVal = getCellValue(a, column);",
  "                let bVal = getCellValue(b, column);",
  "",
  "                // Handle different data types",
  "                if (column === 'rank' || column === 'currentPrice' || column === 'technicalScore' || ",
  "                    column === 'rsi' || column === 'relativeStrength' || column === 'canSlim' || ",
  "                    column === 'minervini' || column === 'fundamental' || column === 'change1D' || ",
  "                    column === 'change1W' || column === 'change1M') {",
  "                    aVal = parseFloat(aVal) || 0;",
  "                    bVal = parseFloat(bVal) || 0;",
  "                } else {",
  "                    aVal = aVal.toString().toLowerCase();",
  "                    bVal = bVal.toString().toLowerCase();",
  "                }",
  "",
  "                if (direction === 'asc') {",
  "                    return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;",
  "                } else {",
  "                    return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;",
  "                }",
  "            });",
  "",
  "            // Re-append sorted rows",
  "            rows.forEach(row => tbody.appendChild(row));",
  "",
  "            // Update current sort state",
  "            currentSort = { column, direction };",
  "        }",
  "",
  "        function getCellValue(row, column) {",
  "            const cells = row.querySelectorAll('td');",
  "            const columnIndex = getColumnIndex(column);",
  "            if (columnIndex >= 0 && cells[columnIndex]) {",
  "                return cells[columnIndex].textContent.trim();",
  "            }",
  "            return '';",
  "        }",
  "",
  "        function getColumnIndex(column) {",
  "            const columnMap = {",
  "                'rank': 0, 'symbol': 1, 'companyName': 2, 'marketCap': 3, 'currentPrice': 4,",
  "                'change1D': 5, 'change1W': 6, 'change1M': 7, 'technicalScore': 8, 'rsi': 9,",
  "                'relativeStrength': 10, 'canSlim': 11, 'minervini': 12, 'fundamental': 13,",
  "                'trendSignal': 14, 'tradingSignal': 15",
  "            };",
  "            return columnMap[column] || 0;",
  "        }",
  ""
)

# Insert the JavaScript
html_content <- c(
  html_content[1:js_insert_pos],
  sorting_js,
  html_content[(js_insert_pos + 1):length(html_content)]
)

# Write the updated HTML file
output_file <- "../../reports/NSE_Interactive_Dashboard_with_Sorting.html"
writeLines(html_content, output_file)

cat("✅ Successfully added sorting functionality to HTML dashboard!\n")
cat("📁 Updated file:", output_file, "\n")
cat("🎯 Features added:\n")
cat("   - Clickable table headers with sort indicators\n")
cat("   - Ascending/descending sort functionality\n")
cat("   - Visual sort direction indicators (↑/↓)\n")
cat("   - Support for all data types (numbers, text, percentages)\n")
