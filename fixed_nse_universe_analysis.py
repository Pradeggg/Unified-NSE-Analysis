#!/usr/bin/env python3
"""
Enhanced NSE Universe Analysis - Python Version
Comprehensive analysis with relative strength focus and error handling
Converted from R script: fixed_nse_universe_analysis.R
"""

import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, date
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

# Try to import technical analysis libraries
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    try:
        import pandas_ta as ta
        TALIB_AVAILABLE = False
        PANDAS_TA_AVAILABLE = True
    except ImportError:
        TALIB_AVAILABLE = False
        PANDAS_TA_AVAILABLE = False
        print("Warning: Neither talib nor pandas_ta available. Technical indicators may be limited.")

# =============================================================================
# Configuration
# =============================================================================

# Set paths — use script location so this works from any directory
BASE_DIR = Path(__file__).resolve().parent
NSE_DATA_DIR = BASE_DIR / 'data'   # nse_sec_full_data.csv and nse_index_data.csv live here
DATA_DIR = BASE_DIR / 'data'
REPORTS_DIR = BASE_DIR / 'reports'
REPORTS_DIR.mkdir(exist_ok=True, parents=True)

# Legacy fallback: OneDrive location for nse_sec_full_data.csv
_ONEDRIVE_NSE = Path('/Users/pgorai/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Data Visualization/Analytics/Financial Markets/NSE-index')

# Database path
DB_PATH = BASE_DIR / 'nse_analysis.db'

# PG: Guard print so it only fires when run directly, not on import
if __name__ == "__main__":
    print("Starting ENHANCED NSE Universe Analysis (Python)...")

# =============================================================================
# Database Functions
# =============================================================================

def initialize_database(db_path):
    """Initialize database with required tables"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create stocks_analysis table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date DATE NOT NULL,
            symbol TEXT NOT NULL,
            company_name TEXT,
            market_cap_category TEXT,
            current_price REAL,
            change_1d REAL,
            change_1w REAL,
            change_1m REAL,
            technical_score REAL,
            rsi REAL,
            trend_signal TEXT,
            relative_strength REAL,
            can_slim_score INTEGER,
            minervini_score INTEGER,
            fundamental_score INTEGER,
            enhanced_fund_score REAL,
            earnings_quality REAL,
            sales_growth REAL,
            financial_strength REAL,
            institutional_backing REAL,
            trading_value REAL,
            trading_signal TEXT,
            UNIQUE(analysis_date, symbol)
        )
    """)
    
    # Create index_analysis table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS index_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date DATE NOT NULL,
            index_name TEXT NOT NULL,
            current_level REAL,
            technical_score REAL,
            rsi REAL,
            momentum_50d REAL,
            relative_strength REAL,
            trend_signal TEXT,
            trading_signal TEXT,
            UNIQUE(analysis_date, index_name)
        )
    """)
    
    # Create market_breadth table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_breadth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date DATE NOT NULL,
            total_stocks INTEGER,
            strong_buy_count INTEGER,
            buy_count INTEGER,
            hold_count INTEGER,
            weak_hold_count INTEGER,
            sell_count INTEGER,
            bullish_percentage REAL,
            bearish_percentage REAL,
            UNIQUE(analysis_date)
        )
    """)
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

# =============================================================================
# Data Loading Functions
# =============================================================================

def load_stock_data():
    """Load NSE stock data from CSV"""
    print("Loading NSE stock data with enhanced error handling...")
    
    # Search order: local data/, then OneDrive legacy location
    candidates = [
        DATA_DIR / 'nse_sec_full_data.csv',
        _ONEDRIVE_NSE / 'nse_sec_full_data.csv',
    ]
    stock_file = next((p for p in candidates if p.exists()), None)
    if stock_file is None:
        raise FileNotFoundError(f"nse_sec_full_data.csv not found in {DATA_DIR} or OneDrive fallback")
    
    try:
        # Read CSV
        df = pd.read_csv(stock_file, encoding='utf-8', low_memory=False)
        
        # Validate required columns
        required_cols = ['SYMBOL', 'TIMESTAMP', 'CLOSE', 'OPEN', 'HIGH', 'LOW', 'TOTTRDQTY', 'TOTTRDVAL']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")
        
        # Clean and convert data types
        df = df[df['SYMBOL'].notna() & (df['SYMBOL'] != '') & df['TIMESTAMP'].notna()].copy()
        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP']).dt.date
        df['CLOSE'] = pd.to_numeric(df['CLOSE'], errors='coerce')
        df['OPEN'] = pd.to_numeric(df['OPEN'], errors='coerce')
        df['HIGH'] = pd.to_numeric(df['HIGH'], errors='coerce')
        df['LOW'] = pd.to_numeric(df['LOW'], errors='coerce')
        df['TOTTRDQTY'] = pd.to_numeric(df['TOTTRDQTY'], errors='coerce')
        df['TOTTRDVAL'] = pd.to_numeric(df['TOTTRDVAL'], errors='coerce')
        
        # Filter valid data
        df = df[df['CLOSE'].notna() & df['TIMESTAMP'].notna() & (df['CLOSE'] > 0) & (df['TOTTRDVAL'] > 0)]
        
        # Remove duplicates - keep highest trading value
        print(f"Before deduplication: {len(df)} records")
        df = df.sort_values(['SYMBOL', 'TIMESTAMP', 'TOTTRDVAL'], ascending=[True, True, False])
        df = df.drop_duplicates(subset=['SYMBOL', 'TIMESTAMP'], keep='first')
        df = df.sort_values(['TIMESTAMP', 'SYMBOL'])
        
        print(f"After deduplication: {len(df)} clean records")
        return df
        
    except Exception as e:
        print(f"Error loading stock data: {e}")
        raise

def load_index_data():
    """Load NSE index data from CSV"""
    print("Loading comprehensive NSE index data...")
    
    candidates = [
        DATA_DIR / 'nse_index_data.csv',
        _ONEDRIVE_NSE / 'nse_index_data.csv',
    ]
    index_file = next((p for p in candidates if p.exists()), None)
    if index_file is None:
        raise FileNotFoundError(f"nse_index_data.csv not found in {DATA_DIR} or OneDrive fallback")
    
    try:
        df = pd.read_csv(index_file, encoding='utf-8', low_memory=False)
        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP']).dt.date
        df['CLOSE'] = pd.to_numeric(df['CLOSE'], errors='coerce')
        df = df[df['CLOSE'].notna() & df['TIMESTAMP'].notna() & (df['CLOSE'] > 0)]
        print(f"Loaded comprehensive index data: {len(df)} records")
        return df
    except Exception as e:
        print(f"Error loading index data: {e}")
        raise

def load_fundamental_data():
    """Load fundamental scores database"""
    print("Loading fundamental scores database...")
    
    fund_file = DATA_DIR / 'fundamental_scores_database.csv'
    if not fund_file.exists():
        fund_file = _ONEDRIVE_NSE / 'fundamental_scores_database.csv'
    if not fund_file.exists():
        print("Fundamental scores file not found, continuing without fundamental data")
        return None
    
    try:
        df = pd.read_csv(fund_file, encoding='utf-8')
        print(f"Loaded fundamental scores data: {len(df)} records")
        return df
    except Exception as e:
        print(f"Error loading fundamental data: {e}")
        return None

def load_company_names():
    """Load company names mapping"""
    print("Loading company names mapping...")
    
    # Try multiple possible locations
    possible_files = [
        DATA_DIR / 'company_names_mapping.csv',
        BASE_DIR / 'archive' / 'company_names_mapping.csv',
        _ONEDRIVE_NSE / 'company_names_mapping.csv',
    ]
    
    for file_path in possible_files:
        if file_path.exists():
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
                print(f"Loaded company names data: {len(df)} records")
                return df
            except Exception as e:
                print(f"Error loading company names: {e}")
    
    print("Company names file not found, continuing without company names")
    return None

# =============================================================================
# Technical Analysis Functions
# =============================================================================

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return None
    return prices.rolling(window=period).mean().iloc[-1]

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    if len(prices) < period + 1:
        return None
    
    if TALIB_AVAILABLE:
        try:
            rsi_values = talib.RSI(prices.values, timeperiod=period)
            return rsi_values[-1] if not np.isnan(rsi_values[-1]) else None
        except:
            pass
    
    # Manual RSI calculation
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None

def calculate_tech_score(stock_data, index_data=None, fundamental_data=None, symbol=None):
    """
    Calculate enhanced technical score with CAN SLIM and Minervini indicators
    Returns dictionary with score, rsi, trend, relative_strength, etc.
    """
    if len(stock_data) < 50:
        return {
            'score': None, 'rsi': None, 'trend': 'NEUTRAL',
            'relative_strength': None, 'can_slim_score': 0,
            'minervini_score': 0, 'fundamental_score': 0
        }
    
    prices = stock_data['CLOSE'].values
    volumes = stock_data['TOTTRDQTY'].values
    current_price = prices[-1]
    
    # Convert to pandas Series for easier calculations
    prices_series = pd.Series(prices)
    volumes_series = pd.Series(volumes)
    
    score = 0
    
    # RSI Score (10 points)
    rsi_val = calculate_rsi(prices_series, 14)
    rsi_score = 0
    if rsi_val is not None:
        if 40 < rsi_val < 70:
            rsi_score = 10
        elif 30 < rsi_val < 80:
            rsi_score = 7
        else:
            rsi_score = 3
    
    # Enhanced Price Trend Score (25 points)
    trend_score = 0
    
    # Calculate SMAs
    sma_10 = calculate_sma(prices_series, 10)
    sma_20 = calculate_sma(prices_series, 20)
    sma_50 = calculate_sma(prices_series, 50)
    sma_100 = calculate_sma(prices_series, 100)
    sma_200 = calculate_sma(prices_series, 200)
    
    # Price vs SMAs (12 points)
    if sma_200 is not None and current_price > sma_200:
        trend_score += 3
    if sma_100 is not None and current_price > sma_100:
        trend_score += 3
    if sma_50 is not None and current_price > sma_50:
        trend_score += 3
    if sma_20 is not None and current_price > sma_20:
        trend_score += 2
    if sma_10 is not None and current_price > sma_10:
        trend_score += 1
    
    # SMA Crossovers (13 points)
    if sma_10 is not None and sma_20 is not None and sma_10 > sma_20:
        trend_score += 3
    if sma_20 is not None and sma_50 is not None and sma_20 > sma_50:
        trend_score += 3
    if sma_50 is not None and sma_100 is not None and sma_50 > sma_100:
        trend_score += 4
    if sma_100 is not None and sma_200 is not None and sma_100 > sma_200:
        trend_score += 3
    
    # Relative Strength Score (25 points)
    relative_strength_score = 0
    relative_strength = None
    
    if index_data is not None and len(index_data) >= 50:
        stock_return = (current_price / prices[max(0, len(prices)-50)]) - 1
        index_prices = index_data['CLOSE'].values
        index_current = index_prices[-1]
        index_50_days_ago = index_prices[max(0, len(index_prices)-50)]
        index_return = (index_current / index_50_days_ago) - 1
        
        relative_strength = stock_return - index_return
        
        if relative_strength > 0.10:
            relative_strength_score = 25
        elif relative_strength > 0.07:
            relative_strength_score = 22
        elif relative_strength > 0.05:
            relative_strength_score = 20
        elif relative_strength > 0.03:
            relative_strength_score = 17
        elif relative_strength > 0.01:
            relative_strength_score = 15
        elif relative_strength > 0:
            relative_strength_score = 12
        elif relative_strength > -0.01:
            relative_strength_score = 10
        elif relative_strength > -0.03:
            relative_strength_score = 7
        elif relative_strength > -0.05:
            relative_strength_score = 5
        elif relative_strength > -0.07:
            relative_strength_score = 2
        else:
            relative_strength_score = 0
    
    # Volume Score (15 points)
    volume_score = 0
    if len(volumes) >= 10:
        vol_avg = np.mean(volumes[-10:])
        current_vol = volumes[-1]
        if current_vol > vol_avg * 1.5:
            volume_score = 15
        elif current_vol > vol_avg:
            volume_score = 10
        elif current_vol > vol_avg * 0.8:
            volume_score = 5
    
    # CAN SLIM Score (25 points)
    can_slim_score = 0
    
    # C - Current Quarterly Earnings (5 points)
    if len(prices) >= 20:
        price_20d_ago = prices[max(0, len(prices)-20)]
        price_momentum_20d = (current_price / price_20d_ago) - 1
        if price_momentum_20d > 0.10:
            can_slim_score += 5
        elif price_momentum_20d > 0.05:
            can_slim_score += 3
        elif price_momentum_20d > 0:
            can_slim_score += 1
    
    # A - Annual Earnings Growth (5 points)
    if len(prices) >= 50:
        price_50d_ago = prices[max(0, len(prices)-50)]
        price_momentum_50d = (current_price / price_50d_ago) - 1
        if price_momentum_50d > 0.20:
            can_slim_score += 5
        elif price_momentum_50d > 0.10:
            can_slim_score += 3
        elif price_momentum_50d > 0.05:
            can_slim_score += 1
    
    # N - New Product/Service (5 points)
    if len(volumes) >= 20:
        vol_20d_avg = np.mean(volumes[-20:])
        current_vol = volumes[-1]
        if current_vol > vol_20d_avg * 2:
            can_slim_score += 5
        elif current_vol > vol_20d_avg * 1.5:
            can_slim_score += 3
        elif current_vol > vol_20d_avg:
            can_slim_score += 1
    
    # S - Supply and Demand (5 points)
    if sma_50 is not None and sma_200 is not None:
        if current_price > sma_50 and sma_50 > sma_200:
            can_slim_score += 5
        elif current_price > sma_50:
            can_slim_score += 3
        elif current_price > sma_200:
            can_slim_score += 1
    
    # L - Leader or Laggard (5 points)
    if relative_strength is not None:
        if relative_strength > 0.10:
            can_slim_score += 5
        elif relative_strength > 0.05:
            can_slim_score += 3
        elif relative_strength > 0:
            can_slim_score += 1
    
    # Minervini Score (20 points)
    minervini_score = 0
    
    # VCP - Volatility Contraction Pattern (6 points)
    if len(prices) >= 20:
        recent_volatility = np.std(prices[-10:]) / np.mean(prices[-10:])
        longer_volatility = np.std(prices[-20:]) / np.mean(prices[-20:])
        if longer_volatility > 0:
            volatility_ratio = recent_volatility / longer_volatility
            if volatility_ratio < 0.7:
                minervini_score += 6
            elif volatility_ratio < 0.9:
                minervini_score += 4
            elif volatility_ratio < 1.1:
                minervini_score += 2
    
    # Base Formation (6 points)
    if len(prices) >= 30:
        recent_high = np.max(prices[-30:])
        recent_low = np.min(prices[-30:])
        price_range = (recent_high - recent_low) / recent_low
        if price_range < 0.15:
            minervini_score += 6
        elif price_range < 0.25:
            minervini_score += 4
        elif price_range < 0.35:
            minervini_score += 2
    
    # Volume Confirmation (8 points)
    if len(volumes) >= 10 and len(prices) >= 10:
        recent_price_change = (prices[-1] - prices[-2]) / prices[-2]
        recent_vol_change = (volumes[-1] - volumes[-2]) / volumes[-2] if volumes[-2] > 0 else 0
        if recent_price_change > 0.02 and recent_vol_change > 0.5:
            minervini_score += 8
        elif recent_price_change > 0.01 and recent_vol_change > 0.2:
            minervini_score += 5
        elif recent_price_change > 0 and recent_vol_change > 0:
            minervini_score += 3
    
    # Fundamental Score (25 points)
    fundamental_score = 0
    enhanced_fund_score = None
    
    if fundamental_data is not None and symbol is not None:
        fund_row = fundamental_data[fundamental_data['symbol'] == symbol]
        if len(fund_row) > 0:
            enhanced_fund_score = fund_row['ENHANCED_FUND_SCORE'].iloc[0]
            if pd.notna(enhanced_fund_score):
                if enhanced_fund_score >= 70:
                    fundamental_score = 25
                elif enhanced_fund_score >= 60:
                    fundamental_score = 20
                elif enhanced_fund_score >= 50:
                    fundamental_score = 15
                elif enhanced_fund_score >= 40:
                    fundamental_score = 10
                elif enhanced_fund_score >= 30:
                    fundamental_score = 5
    
    # Calculate total score (150 points total)
    total_score = (rsi_score + trend_score + relative_strength_score + volume_score + 
                   can_slim_score + minervini_score + fundamental_score)
    
    # Normalize to 0-100 scale
    total_score = round((total_score / 150) * 100, 1)
    
    # Determine trend signal
    trend_signal = "NEUTRAL"
    bullish_count = 0
    bearish_count = 0
    
    if sma_10 is not None and sma_20 is not None:
        if sma_10 > sma_20:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if sma_20 is not None and sma_50 is not None:
        if sma_20 > sma_50:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if sma_50 is not None and sma_100 is not None:
        if sma_50 > sma_100:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if sma_100 is not None and sma_200 is not None:
        if sma_100 > sma_200:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if bullish_count >= 3:
        trend_signal = "STRONG_BULLISH"
    elif bullish_count >= 2:
        trend_signal = "BULLISH"
    elif bearish_count >= 3:
        trend_signal = "STRONG_BEARISH"
    elif bearish_count >= 2:
        trend_signal = "BEARISH"
    
    return {
        'score': total_score,
        'rsi': rsi_val,
        'trend': trend_signal,
        'relative_strength': relative_strength * 100 if relative_strength is not None else None,
        'can_slim_score': can_slim_score,
        'minervini_score': minervini_score,
        'fundamental_score': fundamental_score,
        'enhanced_fund_score': enhanced_fund_score
    }

# =============================================================================
# Main Analysis Function
# =============================================================================

def determine_trading_signal(score):
    """Determine trading signal based on technical score"""
    if score is None or pd.isna(score):
        return "SELL"
    if score >= 80:
        return "STRONG_BUY"
    elif score >= 65:
        return "BUY"
    elif score >= 50:
        return "HOLD"
    elif score >= 35:
        return "WEAK_HOLD"
    else:
        return "SELL"

def get_market_cap_category(price, trading_value):
    """Determine market cap category based on price and trading value"""
    if price >= 1000 and trading_value >= 1000000000:  # 1000+ crores
        return "LARGE_CAP"
    elif price >= 500 and trading_value >= 500000000:  # 500+ crores
        return "MID_CAP"
    elif price >= 200 and trading_value >= 200000000:  # 200+ crores
        return "SMALL_CAP"
    else:
        return "MICRO_CAP"

def analyze_stocks(stock_data, index_data, fundamental_data, company_names, latest_date):
    """Main function to analyze all stocks"""
    print(f"Latest data date: {latest_date}")
    
    # Filter for latest date
    latest_stocks = stock_data[stock_data['TIMESTAMP'] == latest_date].copy()
    latest_stocks = latest_stocks[
        (latest_stocks['CLOSE'].notna()) & 
        (latest_stocks['TOTTRDVAL'].notna()) & 
        (latest_stocks['TOTTRDVAL'] > 0)
    ]
    
    print(f"Total stocks with data on {latest_date}: {len(latest_stocks)}")
    
    # Apply filtering criteria
    filtered_stocks = latest_stocks[
        (latest_stocks['CLOSE'] > 100) & 
        (latest_stocks['TOTTRDQTY'] > 100000)
    ].copy()
    
    print(f"Stocks meeting criteria (Price > ₹100 & Volume > 100,000): {len(filtered_stocks)}")
    print(f"Analyzing {len(filtered_stocks)} filtered stocks for comprehensive analysis")
    
    results = []
    processed_count = 0
    error_count = 0
    
    # Get NIFTY500 index data for relative strength calculation
    # Index CSV uses 'Nifty 500' (mixed case) — match case-insensitively
    nifty500_data = None
    if 'SYMBOL' in index_data.columns:
        mask = index_data['SYMBOL'].str.strip().str.lower() == 'nifty 500'
        nifty500_data = index_data[mask].copy() if mask.any() else None
    
    for idx, stock_row in filtered_stocks.iterrows():
        symbol = stock_row['SYMBOL']
        try:
            # Get historical data for this stock
            stock_history = stock_data[stock_data['SYMBOL'] == symbol].sort_values('TIMESTAMP')
            
            if len(stock_history) < 50:
                continue
            
            # Calculate technical score
            tech_result = calculate_tech_score(
                stock_history, 
                nifty500_data if nifty500_data is not None else None,
                fundamental_data,
                symbol
            )
            
            if tech_result['score'] is None:
                continue
            
            # Calculate price changes
            current_price = stock_row['CLOSE']
            
            # 1D change
            prev_day = stock_history[stock_history['TIMESTAMP'] < latest_date]
            change_1d = None
            if len(prev_day) > 0:
                prev_price = prev_day['CLOSE'].iloc[-1]
                change_1d = ((current_price - prev_price) / prev_price) * 100
            
            # 1W change (5 trading days)
            week_ago = stock_history[stock_history['TIMESTAMP'] < latest_date]
            change_1w = None
            if len(week_ago) >= 5:
                week_price = week_ago['CLOSE'].iloc[-5]
                change_1w = ((current_price - week_price) / week_price) * 100
            
            # 1M change (20 trading days)
            month_ago = stock_history[stock_history['TIMESTAMP'] < latest_date]
            change_1m = None
            if len(month_ago) >= 20:
                month_price = month_ago['CLOSE'].iloc[-20]
                change_1m = ((current_price - month_price) / month_price) * 100
            
            # Get company name
            company_name = symbol
            if company_names is not None:
                name_row = company_names[company_names['SYMBOL'] == symbol]
                if len(name_row) > 0:
                    company_name = name_row['COMPANY_NAME'].iloc[0]
            
            # Determine market cap category
            trading_value = stock_row.get('TOTTRDVAL', 0)
            market_cap = get_market_cap_category(current_price, trading_value)
            
            # Determine trading signal
            trading_signal = determine_trading_signal(tech_result['score'])
            
            result = {
                'SYMBOL': symbol,
                'COMPANY_NAME': company_name,
                'MARKET_CAP_CATEGORY': market_cap,
                'CURRENT_PRICE': round(current_price, 2),
                'CHANGE_1D': round(change_1d, 2) if change_1d is not None else None,
                'CHANGE_1W': round(change_1w, 2) if change_1w is not None else None,
                'CHANGE_1M': round(change_1m, 2) if change_1m is not None else None,
                'TECHNICAL_SCORE': tech_result['score'],
                'RSI': round(tech_result['rsi'], 1) if tech_result['rsi'] is not None else None,
                'RELATIVE_STRENGTH': round(tech_result['relative_strength'], 2) if tech_result['relative_strength'] is not None else None,
                'CAN_SLIM_SCORE': tech_result['can_slim_score'],
                'MINERVINI_SCORE': tech_result['minervini_score'],
                'ENHANCED_FUND_SCORE': tech_result['enhanced_fund_score'],
                'TREND_SIGNAL': tech_result['trend'],
                'TRADING_SIGNAL': trading_signal
            }
            
            results.append(result)
            processed_count += 1
            
            if processed_count % 100 == 0:
                print(f"Processing stock {processed_count} of {len(filtered_stocks)} - {symbol}")
        
        except Exception as e:
            error_count += 1
            # Skip problematic stocks silently
    
        print(f"Processing completed. Successfully processed: {processed_count} stocks. Errors: {error_count}")
    
    return pd.DataFrame(results)

# =============================================================================
# Index Analysis Functions
# =============================================================================

def calculate_index_tech_score(index_data, nifty500_data=None):
    """Calculate technical score for an index"""
    if len(index_data) < 50:
        return {
            'score': None, 'rsi': None, 'trend': 'NEUTRAL',
            'momentum': None, 'relative_strength': None
        }
    
    prices = index_data['CLOSE'].values
    volumes = index_data['TOTTRDQTY'].values if 'TOTTRDQTY' in index_data.columns else None
    current_price = prices[-1]
    
    prices_series = pd.Series(prices)
    
    score = 0
    
    # RSI Score (10 points)
    rsi_val = calculate_rsi(prices_series, 14)
    rsi_score = 0
    if rsi_val is not None:
        if 40 < rsi_val < 70:
            rsi_score = 10
        elif 30 < rsi_val < 80:
            rsi_score = 7
        else:
            rsi_score = 3
    
    # Price Trend Score (25 points)
    trend_score = 0
    
    sma_10 = calculate_sma(prices_series, 10)
    sma_20 = calculate_sma(prices_series, 20)
    sma_50 = calculate_sma(prices_series, 50)
    sma_100 = calculate_sma(prices_series, 100)
    sma_200 = calculate_sma(prices_series, 200)
    
    # Price vs SMAs (12 points)
    if sma_200 is not None and current_price > sma_200:
        trend_score += 3
    if sma_100 is not None and current_price > sma_100:
        trend_score += 3
    if sma_50 is not None and current_price > sma_50:
        trend_score += 3
    if sma_20 is not None and current_price > sma_20:
        trend_score += 2
    if sma_10 is not None and current_price > sma_10:
        trend_score += 1
    
    # SMA Crossovers (13 points)
    if sma_10 is not None and sma_20 is not None and sma_10 > sma_20:
        trend_score += 3
    if sma_20 is not None and sma_50 is not None and sma_20 > sma_50:
        trend_score += 3
    if sma_50 is not None and sma_100 is not None and sma_50 > sma_100:
        trend_score += 4
    if sma_100 is not None and sma_200 is not None and sma_100 > sma_200:
        trend_score += 3
    
    # Volume Score (15 points)
    volume_score = 0
    if volumes is not None and len(volumes) >= 10:
        vol_avg = np.mean(volumes[-10:])
        current_vol = volumes[-1]
        if current_vol > vol_avg * 1.5:
            volume_score = 15
        elif current_vol > vol_avg:
            volume_score = 10
        elif current_vol > vol_avg * 0.8:
            volume_score = 5
    
    # Relative Strength Score (20 points) - vs NIFTY500
    relative_strength_score = 0
    relative_strength = None
    
    if nifty500_data is not None and len(nifty500_data) >= 50:
        index_return = (current_price / prices[max(0, len(prices)-50)]) - 1
        nifty500_prices = nifty500_data['CLOSE'].values
        nifty500_current = nifty500_prices[-1]
        nifty500_50_days_ago = nifty500_prices[max(0, len(nifty500_prices)-50)]
        nifty500_return = (nifty500_current / nifty500_50_days_ago) - 1
        
        relative_strength = index_return - nifty500_return
        
        if relative_strength > 0.10:
            relative_strength_score = 20
        elif relative_strength > 0.07:
            relative_strength_score = 18
        elif relative_strength > 0.05:
            relative_strength_score = 16
        elif relative_strength > 0.03:
            relative_strength_score = 14
        elif relative_strength > 0.01:
            relative_strength_score = 12
        elif relative_strength > 0:
            relative_strength_score = 10
        elif relative_strength > -0.01:
            relative_strength_score = 8
        elif relative_strength > -0.03:
            relative_strength_score = 6
        elif relative_strength > -0.05:
            relative_strength_score = 4
        elif relative_strength > -0.07:
            relative_strength_score = 2
        else:
            relative_strength_score = 0
    
    # Momentum Score (30 points)
    momentum_score = 0
    momentum_50d = None
    if len(prices) >= 50:
        momentum_50d = (current_price / prices[max(0, len(prices)-50)]) - 1
        if momentum_50d > 0.10:
            momentum_score = 30
        elif momentum_50d > 0.07:
            momentum_score = 27
        elif momentum_50d > 0.05:
            momentum_score = 24
        elif momentum_50d > 0.03:
            momentum_score = 21
        elif momentum_50d > 0.01:
            momentum_score = 18
        elif momentum_50d > 0:
            momentum_score = 15
        elif momentum_50d > -0.01:
            momentum_score = 12
        elif momentum_50d > -0.03:
            momentum_score = 9
        elif momentum_50d > -0.05:
            momentum_score = 6
        elif momentum_50d > -0.07:
            momentum_score = 3
    
    total_score = rsi_score + trend_score + relative_strength_score + momentum_score + volume_score
    
    # Determine trend signal
    trend_signal = "NEUTRAL"
    bullish_count = 0
    bearish_count = 0
    
    if sma_10 is not None and sma_20 is not None:
        if sma_10 > sma_20:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if sma_20 is not None and sma_50 is not None:
        if sma_20 > sma_50:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if sma_50 is not None and sma_100 is not None:
        if sma_50 > sma_100:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if sma_100 is not None and sma_200 is not None:
        if sma_100 > sma_200:
            bullish_count += 1
        else:
            bearish_count += 1
    
    if bullish_count >= 3:
        trend_signal = "STRONG_BULLISH"
    elif bullish_count >= 2:
        trend_signal = "BULLISH"
    elif bearish_count >= 3:
        trend_signal = "STRONG_BEARISH"
    elif bearish_count >= 2:
        trend_signal = "BEARISH"
    
    return {
        'score': total_score,
        'rsi': rsi_val,
        'trend': trend_signal,
        'momentum': momentum_50d * 100 if momentum_50d is not None else None,
        'relative_strength': relative_strength * 100 if relative_strength is not None else None
    }

def analyze_nse_indices(index_data, latest_date):
    """Analyze NSE indices"""
    major_indices = [
        "Nifty 50",
        "Nifty 100",
        "Nifty 200",
        "Nifty 500",
        "Nifty Bank",
        "Nifty IT",
        "Nifty Pharma",
        "Nifty Auto",
        "Nifty FMCG",
        "Nifty Metal"
    ]
    
    # Get NIFTY500 data for relative strength calculation
    nifty500_data = None
    if 'SYMBOL' in index_data.columns:
        nifty500_data = index_data[index_data['SYMBOL'].str.upper() == 'NIFTY 500'].copy()
        if len(nifty500_data) > 0:
            nifty500_data = nifty500_data.sort_values('TIMESTAMP')
    
    index_results = []
    
    for index_name in major_indices:
        # Try to find index data
        index_data_subset = None
        
        if 'SYMBOL' in index_data.columns:
            # Try exact match
            index_data_subset = index_data[index_data['SYMBOL'] == index_name].copy()
            
            # Try case-insensitive match
            if len(index_data_subset) == 0:
                index_data_subset = index_data[
                    index_data['SYMBOL'].str.upper() == index_name.upper()
                ].copy()
            
            # Try partial match
            if len(index_data_subset) == 0:
                search_terms = [
                    index_name,
                    index_name.replace(" ", ""),
                    index_name.replace(" ", "_"),
                    index_name.upper(),
                    index_name.lower()
                ]
                for term in search_terms:
                    index_data_subset = index_data[
                        index_data['SYMBOL'].str.contains(term, case=False, na=False)
                    ].copy()
                    if len(index_data_subset) > 0:
                        break
        
        if index_data_subset is not None and len(index_data_subset) >= 50:
            index_data_subset = index_data_subset.sort_values('TIMESTAMP')
            tech_result = calculate_index_tech_score(index_data_subset, nifty500_data)
            
            if tech_result['score'] is not None:
                current_level = index_data_subset['CLOSE'].iloc[-1]
                trading_signal = determine_trading_signal(tech_result['score'])
                
                index_results.append({
                    'INDEX_NAME': index_name,
                    'CURRENT_LEVEL': round(current_level, 2),
                    'TECHNICAL_SCORE': round(tech_result['score'], 1),
                    'RSI': round(tech_result['rsi'], 1) if tech_result['rsi'] is not None else None,
                    'MOMENTUM_50D': round(tech_result['momentum'], 2) if tech_result['momentum'] is not None else None,
                    'RELATIVE_STRENGTH': round(tech_result['relative_strength'], 2) if tech_result['relative_strength'] is not None else None,
                    'TREND_SIGNAL': tech_result['trend'],
                    'TRADING_SIGNAL': trading_signal
                })
    
    return pd.DataFrame(index_results)

# =============================================================================
# Database Saving Functions
# =============================================================================

def save_stocks_to_database(results, latest_date, db_path):
    """Save stocks analysis results to database"""
    conn = sqlite3.connect(str(db_path))
    
    # Prepare data for insertion
    for _, row in results.iterrows():
        try:
            conn.execute("""
                INSERT OR REPLACE INTO stocks_analysis 
                (analysis_date, symbol, company_name, market_cap_category, current_price,
                 change_1d, change_1w, change_1m, technical_score, rsi, trend_signal,
                 relative_strength, can_slim_score, minervini_score, fundamental_score,
                 enhanced_fund_score, trading_signal, trading_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                latest_date, row['SYMBOL'], row.get('COMPANY_NAME', ''),
                row['MARKET_CAP_CATEGORY'], row['CURRENT_PRICE'],
                row.get('CHANGE_1D'), row.get('CHANGE_1W'), row.get('CHANGE_1M'),
                row['TECHNICAL_SCORE'], row.get('RSI'), row['TREND_SIGNAL'],
                row.get('RELATIVE_STRENGTH'), row['CAN_SLIM_SCORE'],
                row['MINERVINI_SCORE'], row.get('ENHANCED_FUND_SCORE', 0),
                row.get('ENHANCED_FUND_SCORE'), row['TRADING_SIGNAL'], 0
            ))
        except Exception as e:
            print(f"Error saving {row['SYMBOL']}: {e}")
    
    conn.commit()
    conn.close()
    print(f"Successfully saved {len(results)} stocks records to database")

def save_indices_to_database(index_results, latest_date, db_path):
    """Save index analysis results to database"""
    if len(index_results) == 0:
        return
    
    conn = sqlite3.connect(str(db_path))
    
    for _, row in index_results.iterrows():
        try:
            conn.execute("""
                INSERT OR REPLACE INTO index_analysis
                (analysis_date, index_name, current_level, technical_score, rsi,
                 momentum_50d, relative_strength, trend_signal, trading_signal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                latest_date, row['INDEX_NAME'], row['CURRENT_LEVEL'],
                row['TECHNICAL_SCORE'], row.get('RSI'),
                row.get('MOMENTUM_50D'), row.get('RELATIVE_STRENGTH'),
                row['TREND_SIGNAL'], row['TRADING_SIGNAL']
            ))
        except Exception as e:
            print(f"Error saving {row['INDEX_NAME']}: {e}")
    
    conn.commit()
    conn.close()
    print(f"Successfully saved {len(index_results)} index records to database")

def save_market_breadth_to_database(results, latest_date, db_path):
    """Save market breadth statistics to database"""
    conn = sqlite3.connect(str(db_path))
    
    signal_counts = results['TRADING_SIGNAL'].value_counts()
    strong_buy = signal_counts.get('STRONG_BUY', 0)
    buy = signal_counts.get('BUY', 0)
    hold = signal_counts.get('HOLD', 0)
    weak_hold = signal_counts.get('WEAK_HOLD', 0)
    sell = signal_counts.get('SELL', 0)
    
    total = len(results)
    bullish = strong_buy + buy
    bearish = sell + weak_hold
    bullish_pct = (bullish / total * 100) if total > 0 else 0
    bearish_pct = (bearish / total * 100) if total > 0 else 0
    
    try:
        conn.execute("""
            INSERT OR REPLACE INTO market_breadth
            (analysis_date, total_stocks, strong_buy_count, buy_count, hold_count,
             weak_hold_count, sell_count, bullish_percentage, bearish_percentage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            latest_date, total, strong_buy, buy, hold, weak_hold, sell,
            bullish_pct, bearish_pct
        ))
        conn.commit()
        print("Saved market breadth record to database")
    except Exception as e:
        print(f"Error saving market breadth: {e}")
    
    conn.close()

# =============================================================================
# Report Generation Functions
# =============================================================================

def generate_markdown_report(results, index_results, latest_date, timestamp):
    """Generate comprehensive markdown report"""
    report_file = REPORTS_DIR / f"NSE_Analysis_Report_{latest_date.strftime('%Y%m%d')}_{timestamp}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# 📊 NSE Market Analysis Report\n\n")
        f.write(f"**Analysis Date:** {latest_date}\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 📈 Analysis Summary\n\n")
        f.write(f"- **Total Stocks Analyzed:** {len(results)}\n")
        f.write(f"- **Filtering Criteria:** Price > ₹100 & Volume > 100,000\n\n")
        
        # Trading signals distribution
        f.write("## 🎯 Trading Signals Distribution\n\n")
        signal_dist = results['TRADING_SIGNAL'].value_counts()
        f.write("| Signal | Count | Percentage |\n")
        f.write("|--------|-------|------------|\n")
        for signal, count in signal_dist.items():
            pct = (count / len(results)) * 100
            f.write(f"| {signal} | {count} | {pct:.1f}% |\n")
        f.write("\n")
        
        # Top performers
        f.write("## 🏆 Top 15 Stocks by Technical Score\n\n")
        top_15 = results.head(15)
        f.write("| Rank | Symbol | Market Cap | Price | 1D | 1W | 1M | Tech Score | RSI | RS | CAN SLIM | Minervini | Trend | Signal |\n")
        f.write("|------|--------|------------|-------|----|----|----|------------|-----|----|----------|-----------|-------|--------|\n")
        for idx, (_, row) in enumerate(top_15.iterrows(), 1):
            f.write(f"| {idx} | {row['SYMBOL']} | {row['MARKET_CAP_CATEGORY']} | "
                   f"₹{row['CURRENT_PRICE']:.2f} | "
                   f"{row.get('CHANGE_1D', 'N/A'):.2f}% | "
                   f"{row.get('CHANGE_1W', 'N/A'):.2f}% | "
                   f"{row.get('CHANGE_1M', 'N/A'):.2f}% | "
                   f"{row['TECHNICAL_SCORE']:.1f} | "
                   f"{row.get('RSI', 'N/A')} | "
                   f"{row.get('RELATIVE_STRENGTH', 'N/A')}% | "
                   f"{row['CAN_SLIM_SCORE']} | "
                   f"{row['MINERVINI_SCORE']} | "
                   f"{row['TREND_SIGNAL']} | "
                   f"{row['TRADING_SIGNAL']} |\n")
        f.write("\n")
        
        # Index analysis
        if len(index_results) > 0:
            f.write("## 📊 Index Analysis\n\n")
            f.write("| Index | Level | Tech Score | RSI | Momentum | RS | Trend | Signal |\n")
            f.write("|-------|-------|------------|-----|----------|----|----|--------|\n")
            for _, row in index_results.iterrows():
                f.write(f"| {row['INDEX_NAME']} | {row['CURRENT_LEVEL']:.2f} | "
                       f"{row['TECHNICAL_SCORE']:.1f} | "
                       f"{row.get('RSI', 'N/A')} | "
                       f"{row.get('MOMENTUM_50D', 'N/A')}% | "
                       f"{row.get('RELATIVE_STRENGTH', 'N/A')}% | "
                       f"{row['TREND_SIGNAL']} | "
                       f"{row['TRADING_SIGNAL']} |\n")
            f.write("\n")
    
    print(f"Markdown report saved to: {report_file}")
    return report_file

# =============================================================================
# Main Execution
# =============================================================================

if __name__ == "__main__":
    try:
        # Initialize database
        initialize_database(DB_PATH)
        print("Database initialized successfully")
        
        # Load data
        stock_data = load_stock_data()
        index_data = load_index_data()
        fundamental_data = load_fundamental_data()
        company_names = load_company_names()
        
        # Get latest date
        latest_date = stock_data['TIMESTAMP'].max()
        print(f"Latest data date: {latest_date}")
        
        # Analyze stocks
        results = analyze_stocks(stock_data, index_data, fundamental_data, company_names, latest_date)
        
        # Sort by technical score
        results = results.sort_values('TECHNICAL_SCORE', ascending=False)
        
        # Analyze indices
        print("\nAnalyzing NSE indices...")
        index_results = analyze_nse_indices(index_data, latest_date)
        print(f"Index analysis completed. Analyzed {len(index_results)} indices.\n")
        
        # Save to database
        print("Saving results to database...")
        save_stocks_to_database(results, latest_date, DB_PATH)
        save_indices_to_database(index_results, latest_date, DB_PATH)
        save_market_breadth_to_database(results, latest_date, DB_PATH)
        
        # Save results to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_str = latest_date.strftime("%d%m%Y")
        output_file = REPORTS_DIR / f"comprehensive_nse_enhanced_{date_str}_{timestamp}.csv"
        results.to_csv(output_file, index=False)
        print(f"\nResults saved to: {output_file}")
        
        # Generate markdown report
        print("\nGenerating comprehensive markdown report...")
        generate_markdown_report(results, index_results, latest_date, timestamp)
        
        # Print summary
        print("\n" + "="*80)
        print("COMPREHENSIVE NSE STOCK UNIVERSE ANALYSIS")
        print(f"Analysis Date: {latest_date}")
        print("="*80 + "\n")
        
        print(f"ANALYSIS SUMMARY:")
        print(f"Total Stocks Analyzed: {len(results)}")
        print(f"Filtering Criteria: Price > ₹100 & Volume > 100,000\n")
        
        # Trading signals distribution
        signal_dist = results['TRADING_SIGNAL'].value_counts()
        print("TRADING SIGNALS DISTRIBUTION:")
        for signal, count in signal_dist.items():
            pct = (count / len(results)) * 100
            print(f"  {signal}: {count} ({pct:.1f}%)")
        
        print("\nTOP 15 STOCKS BY TECHNICAL SCORE:")
        top_15 = results.head(15)
        print(top_15[['SYMBOL', 'MARKET_CAP_CATEGORY', 'CURRENT_PRICE', 'CHANGE_1D', 
                      'CHANGE_1W', 'CHANGE_1M', 'TECHNICAL_SCORE', 'RSI', 
                      'RELATIVE_STRENGTH', 'CAN_SLIM_SCORE', 'MINERVINI_SCORE', 
                      'TREND_SIGNAL', 'TRADING_SIGNAL']].to_string())
        
        if len(index_results) > 0:
            print("\nINDEX ANALYSIS RESULTS:")
            print(index_results[['INDEX_NAME', 'CURRENT_LEVEL', 'TECHNICAL_SCORE', 
                                'RSI', 'MOMENTUM_50D', 'RELATIVE_STRENGTH', 
                                'TREND_SIGNAL', 'TRADING_SIGNAL']].to_string())
        
        print("\n✅ Analysis completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error in analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

