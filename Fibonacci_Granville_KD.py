import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import pyodbc
from config import get_db_connection

# 連接 SQL Server 資料庫
conn = get_db_connection()
cursor = conn.cursor()

strategy_logs = []
def log(text):
    print(text)
    strategy_logs.append(text)


# 計算 RSI 和 5日均量（MA20直接從資料表取得）
def add_rsi_and_volume(df, rsi_period=14, ma_volume_period=5):
    # 計算RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=rsi_period).mean()
    avg_loss = loss.rolling(window=rsi_period).mean()

    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 計算5日均量
    df['MA_volume'] = df['volume'].rolling(window=ma_volume_period).mean()
    
    return df

def calculate_trend_strength(df, period=20):
    """計算趨勢強度"""
    # 計算MA20的5日變化率
    df['MA20_slope'] = df['MA20'].diff(5) / df['MA20'].shift(5) * 100
    
    # 趨勢分類
    df['trend'] = 'neutral'
    df.loc[df['MA20_slope'] > 2, 'trend'] = 'strong_up'
    df.loc[(df['MA20_slope'] > 0) & (df['MA20_slope'] <= 2), 'trend'] = 'up'
    df.loc[(df['MA20_slope'] < 0) & (df['MA20_slope'] >= -2), 'trend'] = 'down'
    df.loc[df['MA20_slope'] < -2, 'trend'] = 'strong_down'
    
    return df


# Fibonacci + RSI 策略
def detect_fibonacci_signals(df, retracements, high, low, tolerance=0.02):
    """Fibonacci回撤策略"""
    buy_signals, sell_signals = [], []
    # 取高點附近的 retracement 作為賣出參考位
    retracement_high = retracements["23.6%"]
    # 依優先順序排列 retracement 作為買進參考位
    retracement_lows = [retracements["78.6%"], retracements["61.8%"], retracements["50.0%"]]
        
    log(f"\n=== Fibonacci 策略檢測 (容差: {tolerance*100:.1f}%) ===")
    log(f"買入參考位: 78.6%({retracements['78.6%']:.2f}), 61.8%({retracements['61.8%']:.2f}), 50.0%({retracements['50.0%']:.2f})")
    log(f"賣出參考位: 23.6%({retracements['23.6%']:.2f})")

    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row['close'])
        rsi = row['RSI']
        volume = row['volume']
        ma_vol = row['MA_volume']
        trend = row['trend'] if 'trend' in row else 'neutral'

        volume_spike = volume > ma_vol * 1.2 if pd.notna(ma_vol) else False  # 提高到1.2倍

        # 買進訊號檢測 - 放寬RSI條件
        if pd.notna(rsi) and rsi < 50:  # 從44放寬到50
            # 動態RSI門檻（根據價格位置調整）
            price_position = (price - low) / (high - low)
            dynamic_rsi_threshold = 40 + price_position * 15  # 40-55的動態範圍
            
            if rsi < dynamic_rsi_threshold and volume_spike:
                fib_level_used = ""
                
                # 按優先順序檢查各個回撤位
                for level_name, rl in [("78.6%", retracements["78.6%"]), 
                                       ("61.8%", retracements["61.8%"]), 
                                       ("50.0%", retracements["50.0%"])]:
                    price_diff_pct = abs(price - rl) / rl
                    
                    # 在下跌或中性趨勢時放寬容差
                    adjusted_tolerance = tolerance * 1.5 if trend in ['down', 'neutral'] else tolerance
                    
                    if price_diff_pct <= adjusted_tolerance:
                        buy_signals.append((row.name, price, rsi, volume, 'Fibonacci'))
                        fib_level_used = level_name          
                        log(f"📈 Fibonacci 買入: {row.name.date()} | 價格: {price:.2f} | RSI: {rsi:.1f} | Fib位準: {fib_level_used}({rl:.2f}) | 偏差: {price_diff_pct*100:.2f}% | 趨勢: {trend}")
                        break
            
        # 賣出訊號檢測 - 避免在強勢上漲時賣出
        if pd.notna(rsi) and rsi > 65 and volume_spike and trend != 'strong_up':
            price_diff_pct = abs(price - retracement_high) / retracement_high
            if price_diff_pct <= tolerance:
                sell_signals.append((row.name, price, rsi, volume, 'Fibonacci'))
                log(f"📉 Fibonacci 賣出: {row.name.date()} | 價格: {price:.2f} | RSI: {rsi:.1f} | Fib位準: 23.6%({retracement_high:.2f}) | 偏差: {price_diff_pct*100:.2f}% | 趨勢: {trend}")
          
    log(f"Fibonacci策略檢測完成: 買入信號 {len(buy_signals)} 個, 賣出信號 {len(sell_signals)} 個")
    return buy_signals, sell_signals



# Granville 簡化邏輯檢測函數
def detect_granville_signals(df, window_size=8, max_break_days=3): # window_size從6改為8
    """
    檢測Granville Rule 2 (假跌破) 和 Rule 6 (假突破) 信號
    """
    granville_buy_signals = []
    granville_sell_signals = []
    
    log(f"\n=== Granville 邏輯檢測 (窗口: {window_size}天, 最大跌破次數: {max_break_days}) ===")
    
    for i in range(window_size, len(df)):
        window = df.iloc[i - window_size + 1:i + 1]  # 取window_size天窗口
        if len(window) < window_size or window['MA20'].isna().any():
            continue
            
        first_day = window.iloc[0]
        last_day = window.iloc[-1]
        middle_days = window.iloc[1:-1]  # 中間天數
        
        # 檢查MA20趨勢方向
        ma20_rising = last_day['MA20'] > first_day['MA20']
        ma20_falling = last_day['MA20'] < first_day['MA20']

        # 成交量變化率
        volume_change_rate = (last_day['volume'] - last_day['MA_volume']) / last_day['MA_volume'] if pd.notna(last_day['MA_volume']) else 0
        
        # Rule 2: 假跌破買入邏輯
        if ma20_rising:
            # 條件1: 第一天股價在MA20之上
            first_above_ma = first_day['close'] >= first_day['MA20']
            
            # 條件2: 期間內跌破MA20次數不超過max_break_days次
            break_count = sum(1 for _, day in middle_days.iterrows() if day['close'] < day['MA20'])
            break_days_ok = break_count <= max_break_days
            
            # 條件3: 最後一天重新站上MA20
            last_above_ma = last_day['close'] >= last_day['MA20']
            
            # 額外條件: RSI和成交量
            rsi_ok = last_day['RSI'] < 60 if pd.notna(last_day['RSI']) else True # 從55放寬到60
            volume_ok = volume_change_rate > 0.1  # 成交量增加20%以上
            
            if first_above_ma and break_days_ok and last_above_ma and rsi_ok and volume_ok:
                granville_buy_signals.append((
                    last_day.name, 
                    last_day['close'], 
                    last_day['RSI'], 
                    last_day['volume'],
                    'Granville_Rule2'
                ))
                log(f"📈 Granville Rule2 買入: {last_day.name.date()} | 價格: {last_day['close']:.2f} | 跌破次數: {break_count} | 成交量變化: {volume_change_rate*100:.1f}%")
        
        # Rule 6: 假突破賣出邏輯
        if ma20_falling:
            # 條件1: 第一天股價在MA20之下
            first_below_ma = first_day['close'] <= first_day['MA20']
            
            # 條件2: 期間內站上MA20次數不超過max_break_days次
            break_count = sum(1 for _, day in middle_days.iterrows() if day['close'] > day['MA20'])
            break_days_ok = break_count <= max_break_days
            
            # 條件3: 最後一天再次跌回MA20之下
            last_below_ma = last_day['close'] <= last_day['MA20']
            
            # 額外條件: RSI和成交量
            rsi_ok = last_day['RSI'] > 50 if pd.notna(last_day['RSI']) else True
            volume_ok = volume_change_rate > 0.1  # 成交量增加10%以上
            
            if first_below_ma and break_days_ok and last_below_ma and rsi_ok and volume_ok:
                granville_sell_signals.append((
                    last_day.name, 
                    last_day['close'], 
                    last_day['RSI'], 
                    last_day['volume'],
                    'Granville_Rule6'
                ))
                log(f"📉 Granville Rule6 賣出: {last_day.name.date()} | 價格: {last_day['close']:.2f} | 突破次數: {break_count} | 成交量變化: {volume_change_rate*100:.1f}%")
    
    return granville_buy_signals, granville_sell_signals

# KD指標交易策略
def detect_kd_signals(df, k_oversold=25, k_overbought=75, d_oversold=25, d_overbought=75):
    """
    KD指標交易策略
    買入信號：
    1. K值和D值都在超賣區域(預設25以下)
    2. K值向上穿越D值(黃金交叉)
    3. 或K值從超賣區域向上突破25
    
    賣出信號：
    1. K值和D值都在超買區域(預設75以上)
    2. K值向下穿越D值(死亡交叉)
    3. 或K值從超買區域向下跌破75
    """
    kd_buy_signals = []
    kd_sell_signals = []
    
    log(f"\n=== KD指標策略檢測 (超賣:{k_oversold}, 超買:{k_overbought}) ===")

    # 記錄上次交易時間，避免頻繁交易
    last_trade_date = None
    min_trade_interval = 3  # 最少間隔3個交易日
    
    for i in range(1, len(df)):
        current = df.iloc[i]
        previous = df.iloc[i-1]
        
        if pd.isna(current['K']) or pd.isna(current['D']) or pd.isna(previous['K']) or pd.isna(previous['D']):
            continue
            
        if last_trade_date is not None:
            days_since_last_trade = (current.name - last_trade_date).days
            if days_since_last_trade < min_trade_interval:
                continue
                
        curr_k, curr_d = current['K'], current['D']
        prev_k, prev_d = previous['K'], previous['D']
        
        trend = current['trend'] if 'trend' in current else 'neutral'
        ma20_direction = 'up' if current['MA20'] > previous['MA20'] else 'down'
        
        # 買入信號檢測 - 放寬條件
        buy_signal = False
        buy_reason = ""
        
        # 條件1: K值向上穿越D值（放寬區域限制）
        if (prev_k <= prev_d and curr_k > curr_d and 
            curr_d <= d_oversold + 20):  # 從15放寬到20
            buy_signal = True
            buy_reason = "KD黃金交叉"
            
        # 條件2: K值從超賣區域向上突破（放寬D值要求）
        elif (prev_k <= k_oversold and curr_k > k_oversold):
            buy_signal = True
            buy_reason = "K值突破超賣區"
            
        # 條件3: K值快速上升
        elif (curr_k - prev_k > 15 and curr_k < 50 and curr_d < 50):
            buy_signal = True
            buy_reason = "K值快速上升"
        
        if buy_signal:
            # 確保D值也在相對低位
            if curr_d > 60 and buy_reason != "K值快速上升":
                buy_signal = False
                
            volume_ok = True
            if pd.notna(current['MA_volume']):
                volume_ok = current['volume'] > current['MA_volume'] * 0.7  # 從0.8放寬到0.7
                
            rsi_ok = True
            if pd.notna(current['RSI']):
                rsi_ok = current['RSI'] < 70  # 從65放寬到70
                
            if volume_ok and rsi_ok and buy_signal:
                kd_buy_signals.append((
                    current.name,
                    current['close'],
                    current['RSI'] if pd.notna(current['RSI']) else 0,
                    current['volume'],
                    f'KD_{buy_reason}'
                ))
                last_trade_date = current.name
                log(f"📈 KD買入: {current.name.date()} | 價格: {current['close']:.2f} | K:{curr_k:.1f} D:{curr_d:.1f} | {buy_reason} | 趨勢: {trend}")

        # 賣出信號檢測 - 避免在強勢上漲時賣出
        sell_signal = False
        sell_reason = ""
        
        # 條件1: K值向下穿越D值且都在超買區域
        if (prev_k >= prev_d and curr_k < curr_d and 
            curr_k >= k_overbought and curr_d >= d_overbought and
            trend != 'strong_up'):  # 避免強勢上漲時賣出
            sell_signal = True
            sell_reason = "KD死亡交叉(超買區)"
            
        # 條件2: K值從超買區域向下跌破（只在非上升趨勢時）
        elif (prev_k >= k_overbought and curr_k < k_overbought and 
              curr_k < curr_d and ma20_direction == 'down'):
            sell_signal = True
            sell_reason = "K值跌破超買區"
            
        if sell_signal:
            # 額外過濾條件：成交量和RSI
            volume_ok = True
            if pd.notna(current['MA_volume']):
                volume_ok = current['volume'] > current['MA_volume'] * 0.8
                
            rsi_ok = True
            if pd.notna(current['RSI']):
                rsi_ok = current['RSI'] > 35  # 避免超跌時賣出
                
            if volume_ok and rsi_ok:
                kd_sell_signals.append((
                    current.name,
                    current['close'],
                    current['RSI'] if pd.notna(current['RSI']) else 0,
                    current['volume'],
                    f'KD_{sell_reason}'
                ))
                last_trade_date = current.name
                log(f"📉 KD賣出: {current.name.date()} | 價格: {current['close']:.2f} | K:{curr_k:.1f} D:{curr_d:.1f} | {sell_reason} | 趨勢: {trend}")

    return kd_buy_signals, kd_sell_signals

# 突破買入策略
def detect_breakout_signals(df, lookback=20, volume_threshold=1.5):
    """
    突破策略：只做買入信號
    """
    breakout_buy_signals = []
    
    log(f"\n=== 突破策略檢測 (回看期: {lookback}天) ===")
    
    for i in range(lookback, len(df)):
        current = df.iloc[i]
        window = df.iloc[i-lookback:i]
        
        period_high = window['high'].max()
        volume_spike = current['volume'] > current['MA_volume'] * volume_threshold if pd.notna(current['MA_volume']) else False
        
        # 買入信號：突破20日高點
        if current['close'] > period_high and volume_spike:
            if pd.notna(current['RSI']) and current['RSI'] < 75:
                breakout_buy_signals.append((
                    current.name,
                    current['close'],
                    current['RSI'],
                    current['volume'],
                    'Breakout_High'
                ))
                log(f"📈 突破買入: {current.name.date()} | 價格: {current['close']:.2f} | 突破{lookback}日高點: {period_high:.2f} | RSI: {current['RSI']:.1f}")
    
    return breakout_buy_signals, []  # 返回空的賣出信號列表

# 信號可靠度確認機制
def filter_signals_by_confirmation(buy_signals, sell_signals, df):
    """改進的多重確認機制 - 更嚴格的買入過濾"""
    
    # 買入信號分組
    buy_by_date = {}
    for signal in buy_signals:
        date = signal[0]
        if date not in buy_by_date:
            buy_by_date[date] = []
        buy_by_date[date].append(signal)
    
    # 賣出信號分組
    sell_by_date = {}
    for signal in sell_signals:
        date = signal[0]
        if date not in sell_by_date:
            sell_by_date[date] = []
        sell_by_date[date].append(signal)
    
    # 更嚴格的買入信號過濾
    filtered_buy = []
    for date, signals in buy_by_date.items():
        if len(signals) >= 2:  # 多重確認優先
            filtered_buy.append(signals[0])
            log(f"✅ 多重確認買入: {date.date()} - {len(signals)}個策略")
        elif len(signals) == 1 and date in df.index:
            signal = signals[0]
            strategy = signal[4]
            price = float(df.loc[date, 'close'])
            ma20 = df.loc[date, 'MA20']
            rsi = df.loc[date, 'RSI']
            volume = df.loc[date, 'volume']
            ma_volume = df.loc[date, 'MA_volume']
            k_value = df.loc[date, 'K'] if 'K' in df.columns else None
            
            confirmed = False
            reason = ""
            
            # 突破策略需要額外確認
            if 'Breakout' in strategy:
                # 需要K值支持或RSI不過高
                if pd.notna(k_value) and k_value < 80:
                    confirmed = True
                    reason = "突破+KD確認"
                elif pd.notna(rsi) and rsi < 70:
                    confirmed = True
                    reason = "突破+RSI確認"
                    
            elif 'KD' in strategy:
                # KD策略需要成交量大增
                if pd.notna(ma_volume) and volume > ma_volume * 1.5:
                    confirmed = True
                    reason = "KD+成交量確認"
                elif pd.notna(ma20) and price <= ma20 * 1.02:
                    confirmed = True
                    reason = "KD+價格確認"
                    
            elif 'Granville' in strategy:
                # Granville需要價格在MA20附近
                if pd.notna(ma20) and abs(price - ma20) / ma20 < 0.02:
                    confirmed = True
                    reason = "Granville+MA20確認"
                    
            elif 'Fibonacci' in strategy:
                # Fibonacci需要RSI確認
                if pd.notna(rsi) and rsi < 45:
                    confirmed = True
                    reason = "Fibonacci+RSI確認"
            
            if confirmed:
                filtered_buy.append(signal)
                log(f"✅ {reason}: {date.date()} - {strategy}")
    
    # 賣出信號過濾 - 也要有確認機制
    filtered_sell = []
    for date, signals in sell_by_date.items():
        if len(signals) >= 2:
            filtered_sell.append(signals[0])
            log(f"✅ 多重確認賣出: {date.date()} - {len(signals)}個策略")
        elif len(signals) == 1 and date in df.index:
            signal = signals[0]
            strategy = signal[4]
            
            # 單一賣出信號也需要確認
            if 'Breakout_Low' in strategy:
                # 跳過突破低點賣出（通常不準）
                continue
            else:
                filtered_sell.append(signal)
                log(f"✅ 單一策略賣出: {date.date()} - {strategy}")
    
    return filtered_buy, filtered_sell

# 處理重複買入信號
def merge_consecutive_signals(buy_signals, sell_signals, merge_window=3):
    """
    合併連續幾天內的重複信號
    merge_window: 合併窗口（天數）
    """
    log(f"\n=== 合併連續信號 (窗口: {merge_window}天) ===")
    
    # 處理買入信號
    merged_buy = []
    if buy_signals:
        buy_signals_sorted = sorted(buy_signals, key=lambda x: x[0])
        
        current_group = [buy_signals_sorted[0]]
        for signal in buy_signals_sorted[1:]:
            days_diff = (signal[0] - current_group[-1][0]).days
            
            if days_diff <= merge_window:
                current_group.append(signal)
            else:
                # 選擇組內最佳信號（價格最低的）
                best_signal = min(current_group, key=lambda x: x[1])
                merged_buy.append(best_signal)
                if len(current_group) > 1:
                    log(f"合併買入信號: {current_group[0][0].date()} 到 {current_group[-1][0].date()} - 選擇 {best_signal[0].date()}")
                current_group = [signal]
        
        # 處理最後一組
        best_signal = min(current_group, key=lambda x: x[1])
        merged_buy.append(best_signal)
        if len(current_group) > 1:
            log(f"合併買入信號: {current_group[0][0].date()} 到 {current_group[-1][0].date()} - 選擇 {best_signal[0].date()}")
    
    # 賣出信號不合併
    return merged_buy, sell_signals
# 關閉資料庫連接
cursor.close()
conn.close()
