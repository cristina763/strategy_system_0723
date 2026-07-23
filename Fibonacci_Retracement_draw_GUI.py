import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle
from config import get_db_connection
from Fibonacci_Granville_KD import (
    add_rsi_and_volume,
    calculate_trend_strength,
    detect_fibonacci_signals,
    detect_granville_signals,
    detect_kd_signals,
    detect_breakout_signals,
    merge_consecutive_signals,
    filter_signals_by_confirmation,
    strategy_logs
)

frame_plot = None
latest_df = None
latest_buy = None
latest_sell = None


def run_analysis(stock_code, start_date, end_date):
    global latest_df, latest_buy, latest_sell

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT [Date], [Open], [Close], [High], [Low], [Volume], [MA20], [K_Value], [D_Value]
        FROM trading_stock
        WHERE StockCode = %s AND [Date] BETWEEN %s AND %s
        ORDER BY [Date] ASC
    """, (stock_code, start_date, end_date))
    rows = cursor.fetchall()
    cols = [col[0] for col in cursor.description]
    df = pd.DataFrame(rows, columns=cols)
    df.rename(columns={"Date": "date", "Close": "close", "Open": "open", "High": "high", "Low": "low",
                       "Volume": "volume", "K_Value": "K", "D_Value": "D"}, inplace=True)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    df = add_rsi_and_volume(df)
    df = calculate_trend_strength(df)

    high = float(df['close'].max())
    low = float(df['close'].min())
    diff = high - low
    retracements = {
        "23.6%": high - 0.236 * diff,
        "38.2%": high - 0.382 * diff,
        "50.0%": high - 0.500 * diff,
        "61.8%": high - 0.618 * diff,
        "78.6%": high - 0.786 * diff,
    }

    fib_buy, fib_sell = detect_fibonacci_signals(df, retracements, high, low, tolerance=0.025)
    gran_buy, gran_sell = detect_granville_signals(df)
    kd_buy, kd_sell = detect_kd_signals(df, k_oversold=30, k_overbought=70)
    breakout_buy, breakout_sell = detect_breakout_signals(df)

    all_buy = fib_buy + gran_buy + kd_buy + breakout_buy
    all_sell = fib_sell + gran_sell + kd_sell + breakout_sell
    merged_buy, merged_sell = merge_consecutive_signals(all_buy, all_sell, merge_window=3)
    final_buy, final_sell = filter_signals_by_confirmation(merged_buy, merged_sell, df)

    final_buy = list({s[0]: s for s in final_buy}.values())
    final_sell = list({s[0]: s for s in final_sell}.values())
    final_buy.sort(key=lambda x: x[0])
    final_sell.sort(key=lambda x: x[0])

    latest_df = df
    latest_buy = final_buy
    latest_sell = final_sell

    plot_signals(df, final_buy, final_sell, retracements, stock_code)
    show_signal_table_and_info(final_buy, final_sell, stock_code, high, low, retracements, [], df)

    cursor.close()
    conn.close()

def plot_signals(df, buy_signals, sell_signals, retracements, stock_code):
    global frame_plot
    has_kd = 'K' in df.columns and 'D' in df.columns and df['K'].notna().sum() > 0 and df['D'].notna().sum() > 0
    fig, ax1 = None, None

    if has_kd:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), height_ratios=[2, 1], sharex=True)
    else:
        fig, ax1 = plt.subplots(figsize=(16, 8))
        ax2 = None

    for date, row in df.iterrows():
        color = 'red' if row['close'] > row['open'] else 'green'
        ax1.add_patch(Rectangle(
            (mdates.date2num(date) - 0.3, min(row['open'], row['close'])),
            0.6,
            abs(row['close'] - row['open']),
            color=color
        ))
        ax1.plot([date, date], [row['low'], row['high']], color=color)

    ax1.plot(df.index, df['MA20'], label='MA20', color='orange', linewidth=2)

    for label, level in retracements.items():
        ax1.axhline(level, color='purple', linestyle='--', label=f"Fib {label}")

    buy_dates = [s[0] for s in buy_signals]
    sell_dates = [s[0] for s in sell_signals]

    if buy_dates:
        ax1.scatter(buy_dates, df.loc[buy_dates]['low'] * 0.99, color='blue', marker='^', s=80, label='Buy')
    if sell_dates:
        ax1.scatter(sell_dates, df.loc[sell_dates]['high'] * 1.01, color='red', marker='v', s=80, label='Sell')

    ax1.legend()
    ax1.set_title(f"{stock_code} Fibonacci + Granville + KD")
    ax1.grid(True)

    if has_kd and ax2 is not None:
        ax2.plot(df.index, df['K'], label='K', color='blue')
        ax2.plot(df.index, df['D'], label='D', color='red')
        # KD參考線
        ax2.axhline(y=80, color='gray', linestyle='--', alpha=0.7, label='Overbought(80)')
        ax2.axhline(y=20, color='gray', linestyle='--', alpha=0.7, label='Oversold(20)')
        ax2.axhline(y=50, color='gray', linestyle=':', alpha=0.5)
        # 額外標示 KD 策略信號點
        kd_only_buy_signals = [s for s in buy_signals if 'KD_' in str(s[4])]
        kd_only_sell_signals = [s for s in sell_signals if 'KD_' in str(s[4])]

        # KD 買進信號
        if kd_only_buy_signals:
            kd_buy_dates = [s[0] for s in kd_only_buy_signals if s[0] in df.index and pd.notna(df.loc[s[0], 'K'])]
            kd_buy_k_values = [df.loc[d, 'K'] for d in kd_buy_dates]
            ax2.scatter(kd_buy_dates, kd_buy_k_values, marker='o', label='KD Buy', color='blue', 
                        s=80, edgecolors='white', linewidths=1, zorder=5)

        # KD 賣出信號
        if kd_only_sell_signals:
            kd_sell_dates = [s[0] for s in kd_only_sell_signals if s[0] in df.index and pd.notna(df.loc[s[0], 'K'])]
            kd_sell_k_values = [df.loc[d, 'K'] for d in kd_sell_dates]
            ax2.scatter(kd_sell_dates, kd_sell_k_values, marker='o', label='KD Sell', color='red', 
                        s=80, edgecolors='white', linewidths=1, zorder=5)

        ax2.legend()
        ax2.set_ylabel("KD value")
        ax2.set_ylim(0, 100)
        ax2.grid(True, alpha=0.3)
        ax2.set_title("KD Stochastic Oscillator", fontsize=12)

    for widget in frame_plot.winfo_children():
        widget.destroy()
    canvas = FigureCanvasTkAgg(fig, frame_plot)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

def show_signal_table_and_info(buy_signals, sell_signals, stock_code, high, low, retracements, granville_logs, df):
    win = tk.Toplevel()
    win.title(f"{stock_code} 策略分析細節")
    win.geometry("1200x600")

    left = ttk.Frame(win)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    right = ttk.Frame(win)
    right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    ttk.Label(left, text="交易信號", font=("Arial", 12, "bold")).pack(anchor=tk.W)
    tree = ttk.Treeview(left, columns=("日期", "價格", "RSI", "量", "策略"), show="headings", height=20)
    for col in ("日期", "價格", "RSI", "量", "策略"):
        tree.heading(col, text=col)
        tree.column(col, width=100)
    for s in buy_signals:
        tree.insert('', tk.END, values=(s[0].date(), f"{s[1]:.2f}", f"{s[2]:.1f}", int(s[3]), s[4]), tags=('buy',))
    for s in sell_signals:
        tree.insert('', tk.END, values=(s[0].date(), f"{s[1]:.2f}", f"{s[2]:.1f}", int(s[3]), s[4]), tags=('sell',))
    tree.tag_configure('buy', background="#ddffdd")
    tree.tag_configure('sell', background="#ffdddd")
    tree.pack(fill=tk.BOTH, expand=True)

    ttk.Label(right, text="策略分析細節", font=("Arial", 12, "bold")).pack(anchor=tk.W)
    text = tk.Text(right, wrap="word")
    text.pack(fill=tk.BOTH, expand=True)
    text.insert(tk.END, f"=== {stock_code} Fibonacci 回撤位準 ===\n最高: {high:.2f}\n最低: {low:.2f}\n")
    for level, price in retracements.items():
        text.insert(tk.END, f"{level}: {price:.2f}\n")
    if 'K' in df.columns and 'D' in df.columns:
        text.insert(tk.END, "\n=== KD 指標 ===\n")
        text.insert(tk.END, f"K 範圍: {df['K'].min():.1f} - {df['K'].max():.1f}\n")
        text.insert(tk.END, f"D 範圍: {df['D'].min():.1f} - {df['D'].max():.1f}\n")
    text.insert(tk.END, "\n=== 策略分析紀錄輸出 ===\n")
    if strategy_logs:
        for log_line in strategy_logs:
            text.insert(tk.END, log_line + "\n")
    else:
        text.insert(tk.END, "（無策略紀錄）\n")
    text.config(state=tk.DISABLED)
    
def simulate_backtest(initial_cash):
    print("【回測績效模擬】")
    print("="*100)

    df = latest_df.copy()
    final_buy_signals = latest_buy
    final_sell_signals = latest_sell

    cash = initial_cash
    stock = 0
    last_buy_price = 0
    trade_log = []
    min_hold_days = 10
    last_buy_date = None

    k_overbought = 80
    d_overbought = 80

    def is_multi_confirm(buy_signal):
        src = str(buy_signal[4])
        return ("確認" in src or "+" in src or "Breakout" in src or "Fibonacci" in src or "Granville" in src)

    # 過濾買進信號
    filtered_buy_signals = [s for s in final_buy_signals if is_multi_confirm(s)]

    # 合併並排序所有信號
    all_signals = []
    for s in filtered_buy_signals:
        all_signals.append((s[0], 'buy', s[1], s[4]))
    for s in final_sell_signals:
        date = s[0]
        k = df.loc[date, 'K'] if date in df.index and 'K' in df.columns else 0
        d = df.loc[date, 'D'] if date in df.index and 'D' in df.columns else 0
        if "KD死亡交叉" in str(s[4]):
            if k < k_overbought or d < d_overbought:
                continue
        all_signals.append((date, 'sell', s[1], s[4]))
    all_signals.sort(key=lambda x: x[0])

    # 每日收盤價
    close_dict = {pd.to_datetime(idx): row['close'] for idx, row in df.iterrows()}

    for date, action, price, strategy in all_signals:
        if stock > 0 and last_buy_price > 0:
            curr_close = close_dict.get(date, price)
            gain = (float(curr_close) - float(last_buy_price)) / float(last_buy_price)
            if gain >= 0.10:
                cash += stock * float(curr_close)
                trade_log.append((date, '停利賣出', curr_close, stock, cash, '停利'))
                stock = 0
                last_buy_date = None
                continue
            elif gain <= -0.07:
                cash += stock * float(curr_close)
                trade_log.append((date, '停損賣出', curr_close, stock, cash, '停損'))
                stock = 0
                last_buy_date = None
                continue

        if action == 'buy':
            if stock == 0:
                stock = int(float(cash) // float(price))
                used_cash = stock * float(price)
                cash -= used_cash
                last_buy_price = price
                last_buy_date = date
                trade_log.append((date, '買進', price, stock, cash, strategy))
        elif action == 'sell':
            if stock > 0 and last_buy_date and (date - last_buy_date).days >= min_hold_days:
                cash += float(stock * price)
                trade_log.append((date, '賣出', price, stock, cash, strategy))
                stock = 0
                last_buy_date = None

    # 期末強制賣出
    final_date = df.index[-1]
    final_close = df.iloc[-1]['close']
    if stock > 0:
        cash += stock * float(final_close)
        trade_log.append((final_date, '期末賣出', final_close, stock, cash, '期末結算'))
        stock = 0

    # 輸出結果
    show_backtest_result_window(initial_cash, cash, trade_log)



def show_backtest_result_window(initial_cash, cash, trade_log):
    win = tk.Toplevel()
    win.title("回測結果")
    win.geometry("800x500")

    text = tk.Text(win, wrap="word")
    text.pack(fill=tk.BOTH, expand=True)

    text.insert(tk.END, "日期         | 動作   | 價格    | 股數    | 剩餘現金   | 策略\n")
    text.insert(tk.END, "-"*70 + "\n")
    for d, act, price, shares, left_cash, strat in trade_log:
        text.insert(tk.END, f"{d.date()} | {act:6s} | {price:7.2f} | {shares:6d} | {left_cash:10,.0f} | {strat}\n")
    total_return = cash - initial_cash
    total_return_pct = total_return / initial_cash * 100
    text.insert(tk.END, "-"*70 + "\n")
    text.insert(tk.END, f"初始資金：{initial_cash:,.0f}\n期末資金：{cash:,.0f}\n總損益：{total_return:,.0f} 元  ({total_return_pct:.2f}%)\n")
    text.config(state=tk.DISABLED)


def create_tab3(tab3):
    global frame_plot
    tab3.title = "策略分析與圖表"
    frame_input = ttk.Frame(tab3)
    frame_input.pack(pady=10)

    ttk.Label(frame_input, text="股票代碼:").pack(side=tk.LEFT)
    entry_code = ttk.Entry(frame_input, width=10)
    entry_code.pack(side=tk.LEFT, padx=5)

    ttk.Label(frame_input, text="開始日期 (YYYY-MM-DD):").pack(side=tk.LEFT)
    entry_start = ttk.Entry(frame_input, width=12)
    entry_start.pack(side=tk.LEFT, padx=5)

    ttk.Label(frame_input, text="結束日期 (YYYY-MM-DD):").pack(side=tk.LEFT)
    entry_end = ttk.Entry(frame_input, width=12)
    entry_end.pack(side=tk.LEFT, padx=5)

    ttk.Label(frame_input, text="本金:").pack(side=tk.LEFT)
    entry_cash = ttk.Entry(frame_input, width=10)
    entry_cash.pack(side=tk.LEFT, padx=5)

    def on_click():
        code = entry_code.get().strip()
        start = entry_start.get().strip()
        end = entry_end.get().strip()
        if code and start and end:
            try:
                run_analysis(code, start, end)
            except Exception as e:
                messagebox.showerror("錯誤", str(e))
        else:
            messagebox.showwarning("請填寫所有欄位", "請輸入股票代碼與日期區間")

    def on_simulate():
        try:
            cash = int(entry_cash.get().strip())
            simulate_backtest(cash)
        except:
            messagebox.showwarning("輸入錯誤", "請輸入正確的本金數字")

    ttk.Button(frame_input, text="執行分析", command=on_click).pack(side=tk.LEFT, padx=10)
    ttk.Button(frame_input, text="模擬回測", command=on_simulate).pack(side=tk.LEFT, padx=10)

    frame_plot = ttk.Frame(tab3)
    frame_plot.pack(fill=tk.BOTH, expand=True)

