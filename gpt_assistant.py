import tkinter as tk
from tkinter import messagebox, scrolledtext
import pandas as pd
from config import get_db_connection, get_openai_client

# GPT API 初始化
# 資料庫查詢函式
def get_stock_data(stock_code, start_date, end_date):
    conn = None
    try:
        conn = get_db_connection()
        query = f"""
            SELECT *
            FROM trading_stock
            WHERE StockCode = '{stock_code}'
            AND Date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY Date
        """
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        messagebox.showerror("資料庫錯誤", f"查詢過程出現錯誤：{e}")
        return pd.DataFrame()
    finally:
        if conn is not None:
            conn.close()

# 將 DataFrame 轉為 CSV 純文字
def dataframe_to_text(df):
    return df.to_csv(index=False)

# GPT 趨勢分析
def ask_gpt_about_stock(data_text):
    prompt = f"""
我提供一段股票訊號與價格資訊，請你根據技術分析，提供詳細的分析建議，並說明目前可能的趨勢方向、是否應持股或觀望。
以下是資料：
{data_text}
"""
    response = get_openai_client().chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "你是一位技術分析的投資顧問"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

# 主功能 tab 建立函式
def create_tab1(tab):
    # 區域變數可在內部函式共用
    def run_range_query():
        stock_code = entry_code.get().strip()
        start_date = entry_start.get().strip()
        end_date = entry_end.get().strip()

        if not stock_code or not start_date or not end_date:
            messagebox.showwarning("提醒", "請輸入完整的股票代碼與日期區間")
            return

        output_text.delete("1.0", tk.END)
        output_text.insert(tk.END, "正在查詢資料...\n")
        tab.update()

        df = get_stock_data(stock_code, start_date, end_date)
        if df.empty:
            output_text.insert(tk.END, "\n查無資料或發生錯誤")
            return

        # 取得使用者選取的欄位
        selected_indices = listbox_columns.curselection()
        selected_cols = [listbox_columns.get(i) for i in selected_indices]

        if not selected_cols:
            messagebox.showwarning("提醒", "請至少選擇一個欄位")
            return

        try:
            df = df[selected_cols]
        except Exception as e:
            output_text.insert(tk.END, f"\n欄位錯誤：{e}")
            return

        df_text = dataframe_to_text(df)

        output_text.insert(tk.END, "\n\n進行技術分析中...\n")
        tab.update()
        suggestion = ask_gpt_about_stock(df_text)
        output_text.insert(tk.END, f"\n技術分析建議：\n{suggestion}")

    # 股票輸入區
    frame_input = tk.Frame(tab)
    frame_input.pack(pady=10, padx=10, fill="x")

    tk.Label(frame_input, text="股票代碼：").grid(row=0, column=0, sticky="e")
    entry_code = tk.Entry(frame_input, width=10)
    entry_code.grid(row=0, column=1, padx=5)

    tk.Label(frame_input, text="起始日期（YYYY-MM-DD）：").grid(row=0, column=2, sticky="e")
    entry_start = tk.Entry(frame_input, width=12)
    entry_start.grid(row=0, column=3, padx=5)

    tk.Label(frame_input, text="結束日期（YYYY-MM-DD）：").grid(row=0, column=4, sticky="e")
    entry_end = tk.Entry(frame_input, width=12)
    entry_end.grid(row=0, column=5, padx=5)

    tk.Button(frame_input, text="分析", command=run_range_query, width=20).grid(row=0, column=6, padx=10)

    # 多選欄位清單
    tk.Label(frame_input, text="選擇分析欄位：").grid(row=1, column=0, sticky="ne", pady=10)
    listbox_columns = tk.Listbox(frame_input, selectmode="multiple", height=6, exportselection=False)
    all_columns = ["Date", "Open", "High", "Low", "Close", "Volume", "Change",
                   "MA5", "MA10", "MA20", "MA60", "MA120", "MA240", "K_value", "D_value"]
    for col in all_columns:
        listbox_columns.insert(tk.END, col)
    listbox_columns.grid(row=1, column=1, columnspan=5, sticky="w", padx=5)

    # 輸出區
    tk.Label(tab, text="結果與技術分析：").pack(anchor='w', padx=10)
    output_text = scrolledtext.ScrolledText(tab, height=30, font=("Courier", 12))
    output_text.pack(fill="both", expand=True, padx=10, pady=5)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("股市技術分析助手")
    root.geometry("1000x700")

    tab_frame = tk.Frame(root)
    tab_frame.pack(fill="both", expand=True)

    create_tab1(tab_frame)

    root.mainloop()
