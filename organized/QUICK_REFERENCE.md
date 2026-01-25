# 🚀 QUICK REFERENCE CARD - NSE ANALYSIS SYSTEM

## 🎯 Essential Commands

### Run Complete Analysis
```r
source('organized/core_scripts/complete_integrated_analysis.R')
run_complete_integrated_analysis()
```

### Run Backtesting Only
```r
source('organized/core_scripts/run_backtesting_on_latest.R')
```

### View Latest Dashboard
Open: `organized/reports/latest_dashboard.html`

---

## 📊 Top 5 High Confidence Stocks (Latest)

| Stock | Technical Score | Confidence | Signal | Return | Win Rate |
|-------|----------------|------------|--------|--------|----------|
| CREDITACC | 81.3 | 92.5% | STRONG_BUY | +33.1% | 80.8% |
| AARVI | 75.3 | 90.1% | BUY | +9.3% | 67.7% |
| BOSCHLTD | 74.7 | 89.9% | BUY | +11.0% | 68.1% |
| ASHAPURMIN | 73.3 | 89.3% | BUY | +10.5% | 76.6% |
| ASIANENE | 72.7 | 89.1% | BUY | +18.1% | 73.8% |

---

## 📈 Key Statistics

- **Total Stocks Analyzed:** 1,951
- **Very High Confidence (≥80%):** 88 stocks
- **High Confidence (≥70%):** 265 stocks
- **Average Confidence:** 49.9%
- **Strong Buy Signals:** 2 stocks
- **Buy Signals:** 30 stocks

---

## 🎯 Trading Signals

- **STRONG_BUY (≥80):** Highest confidence
- **BUY (≥65):** Positive signals  
- **HOLD (≥50):** Neutral positions
- **WEAK_HOLD (≥35):** Cautious positions
- **SELL (<35):** Negative signals

---

## 📁 Important Files

### Core Scripts
- `organized/core_scripts/fixed_nse_universe_analysis.R` - Main engine
- `organized/core_scripts/complete_integrated_analysis.R` - Complete workflow
- `organized/core_scripts/backtesting_engine.R` - Backtesting engine

### Latest Results
- `organized/reports/latest_dashboard.html` - Interactive dashboard
- `organized/analysis_results/latest_comprehensive_analysis.csv` - Analysis data
- `organized/backtesting_results/latest_backtesting_results.csv` - Backtesting data

### Documentation
- `organized/FINAL_PROJECT_SUMMARY.md` - Complete project overview
- `organized/documentation/README.md` - Setup instructions

---

## 🔧 Technical Scoring Components

1. **RSI Score (8 pts):** 40-70 optimal range
2. **Price vs SMAs (10 pts):** Above moving averages
3. **SMA Crossovers (10 pts):** Moving average crossovers
4. **Relative Strength (20 pts):** vs NIFTY500
5. **Volume Score (12 pts):** vs 10-day average
6. **CAN SLIM Score (20 pts):** William O'Neil method
7. **Minervini Score (20 pts):** Mark Minervini method
8. **Fundamental Score (25 pts):** Enhanced fundamentals

---

## 🎯 Confidence Score Formula

- **RSI Confidence (30%):** Based on RSI ranges
- **Technical Score Confidence (40%):** Normalized score
- **Relative Strength Confidence (30%):** vs NIFTY500

---

## 📊 Market Cap Performance

- **Large Cap:** 49 stocks, Avg Score: 41.6
- **Mid Cap:** 100 stocks, Avg Score: 37.4  
- **Small Cap:** 139 stocks, Avg Score: 35.8
- **Micro Cap:** 1,663 stocks, Avg Score: 29.6

---

## 🚨 Quick Troubleshooting

### If analysis fails:
1. Check data files in `organized/data/`
2. Verify R packages: dplyr, lubridate, ggplot2
3. Check file permissions

### If backtesting fails:
1. Ensure analysis results exist
2. Check latest CSV files in reports/
3. Verify backtesting engine loaded

### If dashboard doesn't load:
1. Check HTML file exists in `organized/reports/`
2. Open in modern browser
3. Check file permissions

---

## 📞 Support

- **Project Documentation:** `organized/FINAL_PROJECT_SUMMARY.md`
- **Backtesting Guide:** `organized/documentation/BACKTESTING_SYSTEM_OVERVIEW.md`
- **Setup Instructions:** `organized/documentation/README.md`

---

*Last Updated: September 1, 2025*
