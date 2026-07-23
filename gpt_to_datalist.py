import tkinter as tk
from tkinter import messagebox, scrolledtext
import pandas as pd
from config import get_db_connection, get_openai_client


# 用 GPT 產生 SQL 語句
def generate_sql(instruction):
    # Prompt 告訴 GPT 如何根據自然語言需求產生符合 SQL Server 格式的 SQL 指令
    prompt = f"""
你是一位資料庫工程師。請根據以下使用者的描述，判斷這是要「查詢」還是「更新」還是「更改」資料，並產生對資料表的正確 SQL 指令，只回傳 SQL 語句，不附加說明，不加```sql 或 ``` 等包裝標記，不加 -- 等註解。

trading_stock_test 資料表欄位有：Date, StockCode, Capacity, Volume, Open, High, Low, Close, Change, Transaction, MA5, MA10, MA20, MA60, MA120, MA240, K_value, D_value。

- 所有欄位名稱都必須加上中括號（如 [Close], [K_value]）
- 若用 [Date] 查詢，請使用 CAST([Date] AS DATE)
- 如果你使用 UNION ALL 並搭配 ORDER BY，請將每個子查詢包在 SELECT * FROM (...) AS 別名 裡，並於子查詢中使用 TOP N（如 TOP 1）才能被 SQL Server 接受。
- 不要提供註解或說明。
- 不要使用 ```sql 或 ``` 等包裝標記。
- 若需要多段 SQL 指令，請用分號分隔即可。
- 若用 UNION 搭配 TOP + ORDER BY，請將每段查詢包在 SELECT * FROM (...) 中，並給定別名（如 MaxRise, MaxDrop），避免語法錯誤。

使用者描述：
{instruction}
"""
    # 呼叫 GPT 產生回應
    res = get_openai_client().chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "你是一位熟悉 SQL 的資料庫工程師"},
            {"role": "user", "content": prompt}
        ]
    )
    # 回傳 GPT 回傳的 SQL 指令，移除前後空白
    return res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

# 若 SQL 執行錯誤，請 GPT 協助修正 SQL 的函式
def fix_sql_with_gpt(user_prompt, sql_attempted, error_message):
    # 包含原始需求、錯誤 SQL、錯誤訊息，請 GPT 幫忙修正
    prompt = f"""
你是一位熟悉 SQL Server 的資料庫工程師，我剛使用以下自然語言需求產生 SQL，但執行時出錯。

請你幫我修正這段 SQL。注意：只回傳正確的 SQL 指令，不要說明、不加註解、不加 ```sql ``` 或 ``` 。
如果你使用 UNION ALL 並搭配 ORDER BY，請將每個子查詢包在 SELECT * FROM (...) AS 別名 裡，並於子查詢中使用 TOP N（如 TOP 1）才能被 SQL Server 接受。
原始需求：
{user_prompt}

原始 SQL：
{sql_attempted}

錯誤訊息：
{error_message}
"""
    # 呼叫 GPT 修正錯誤的 SQL
    res = get_openai_client().chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "你是一位熟悉 SQL 的資料庫工程師"},
            {"role": "user", "content": prompt}
        ]
    )
    # 回傳修正後的 SQL，並移除可能會有的包裝標記（例如 GPT 回傳時加上的 ```sql）
    return res.choices[0].message.content.strip().replace("```sql", "").replace("```", "").strip()

# 嘗試查詢資料庫，若失敗則自動請 GPT 修正 SQL 再試一次
def execute_query_with_retry(sql, user_prompt):
    conn = None
    try:
        conn = get_db_connection()
        # 嘗試用 pandas 直接執行 SQL 並轉成 DataFrame
        df = pd.read_sql(sql, conn)
        return df.to_string(index=False)
    except Exception as e:
        # 若執行錯誤，顯示錯誤訊息並讓 GPT 修正
        error_msg = str(e)
        print("初次查詢錯誤，嘗試讓 GPT 修正 SQL...")
        fixed_sql = fix_sql_with_gpt(user_prompt, sql, error_msg)
        try:
            # 修正後再執行一次
            df = pd.read_sql(fixed_sql, conn)
            return f"原始查詢失敗，已修正 SQL：\n{fixed_sql}\n\n修正查詢結果：\n" + df.to_string(index=False)
        except Exception as e2:
            return f"修正後仍查詢失敗：{e2}\n修正 SQL：\n{fixed_sql}"
    finally:
        if conn is not None:
            conn.close()

# 執行sql
def execute_update(sql, user_prompt):
    conn = None
    try:
        conn = get_db_connection()
        # 執行SQL並提交
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        return "成功更新資料"
    except Exception as e:
        error_msg = str(e)
        print("初次修正錯誤，嘗試讓 GPT 修正 SQL...")
        fixed_sql = fix_sql_with_gpt(user_prompt, sql, error_msg)
        try:
            # 修正後再執行一次
            df = pd.read_sql(fixed_sql, conn)
            return f"原始修改失敗，已修正 SQL：\n{fixed_sql}\n\n修正查詢結果：\n" + df.to_string(index=False)
        except Exception as e2:
            return f"修正後仍失敗：{e2}\n修正 SQL：\n{fixed_sql}"
    finally:
        if conn is not None:
            conn.close()


# 建立 GUI 中的第二個頁籤（供使用者輸入需求 → 產生 SQL → 顯示查詢或更新結果）
def create_tab2(tab):
    # 這些元件需在內部函式中共享
    # 執行 SQL 的內部函式
    def run_sql():
        # 讀取輸入區文字
        user_input = input_text.get("1.0", tk.END).strip()
        if not user_input:
            messagebox.showwarning("提醒", "請輸入")
            return
        
        output_text.delete("1.0", tk.END)
        output_text.insert(tk.END, "正在產生 SQL...\n")
        tab.update()

        # 呼叫 GPT 產生 SQL
        sql_cmd = generate_sql(user_input)
        output_text.insert(tk.END, f"\n產生 SQL：\n{sql_cmd}\n")

        # 根據語句開頭判斷是哪一種操作
        if sql_cmd.strip().lower().startswith("select"):
            result = execute_query_with_retry(sql_cmd, user_input)
            output_text.insert(tk.END, f"\n查詢結果：\n{result}")
        elif sql_cmd.strip().lower().startswith("update"):
            # 若為更新，詢問使用者是否執行
            confirm = messagebox.askyesno("確認", "是否要執行這段 UPDATE 指令？")
            if confirm:
                result = execute_update(sql_cmd, user_input)
                output_text.insert(tk.END, f"\n{result}")
            else:
                output_text.insert(tk.END, "\n已取消更新。")
        elif sql_cmd.strip().lower().startswith("delete"):
            confirm = messagebox.askyesno("確認", "是否要執行這段 DELETE 指令？")
            if confirm:
                result = execute_update(sql_cmd, user_input)
                output_text.insert(tk.END, f"\n{result}")
            else:
                output_text.insert(tk.END, "\n已取消更新。")
        else:
            result = execute_update(sql_cmd, user_input)
            output_text.insert(tk.END, f"\n{result}")

    # 執行技術分析（使用 GPT 進行評論）
    def run_tech_analysis():
        data_text = output_text.get("1.0", tk.END).strip()
        if not data_text:
            messagebox.showwarning("提醒", "請先執行查詢後再分析")
            return
        output_text.insert(tk.END, "\n\n技術分析中...\n")
        tab.update()
        result = ask_gpt_about_stock(data_text)
        output_text.insert(tk.END, f"\n技術分析建議：\n{result}")

    # GUI 組件建立（輸入區、按鈕、輸出區）
    tk.Label(tab, text="輸入需求：").pack(anchor='w')
    input_text = scrolledtext.ScrolledText(tab, height=5, font=("Courier", 12))
    input_text.pack(fill="x", padx=10)

    btn_frame = tk.Frame(tab)
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="產生 SQL 並執行", command=run_sql, width=20).pack(side="left", padx=5)

    tk.Label(tab, text="執行結果：").pack(anchor='w')
    output_text = scrolledtext.ScrolledText(tab, height=25, font=("Courier", 12))
    output_text.pack(fill="both", expand=True, padx=10, pady=5)
