import json
import tkinter as tk
from tkinter import messagebox, scrolledtext

import pandas as pd

from config import (
    get_db_connection,
    get_max_analysis_chars,
    get_max_query_rows,
    get_openai_client,
    get_openai_model,
)
from gpt_assistant import ask_gpt_about_stock
from query_service import (
    ALLOWED_COLUMNS,
    QueryPlanError,
    build_select_query,
    write_audit_event,
)


def _parse_json_object(text):
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise QueryPlanError("模型未回傳有效的 JSON 查詢計畫")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise QueryPlanError("模型回傳的查詢計畫不是有效 JSON") from error


def generate_query_plan(instruction):
    schema = {
        "operation": "select",
        "columns": ["Date", "StockCode", "Close", "Volume"],
        "filters": [
            {"column": "StockCode", "operator": "=", "value": "2330"}
        ],
        "order_by": [{"column": "Date", "direction": "DESC"}],
        "limit": 100,
    }
    prompt = f"""
將使用者需求轉換成唯讀股票資料查詢計畫。
只回傳一個 JSON object，不要回傳 SQL、Markdown 或說明。
operation 必須是 select。
可用欄位：{", ".join(ALLOWED_COLUMNS)}
filters 的 operator 只能使用 =、!=、>、>=、<、<=、LIKE。
order_by 的 direction 只能使用 ASC 或 DESC。
最多回傳 {get_max_query_rows()} 筆資料。
不得建立、修改或刪除任何資料。
不得加入 JSON schema 以外的欄位。

格式範例：
{json.dumps(schema, ensure_ascii=False)}

使用者需求：
{instruction}
"""
    response = get_openai_client().chat.completions.create(
        model=get_openai_model(),
        messages=[
            {
                "role": "system",
                "content": "你只負責建立唯讀、結構化、可驗證的查詢計畫。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return _parse_json_object(response.choices[0].message.content)


def execute_readonly_query(sql, parameters):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(sql, tuple(parameters))
        rows = cursor.fetchall()
        columns = [item[0] for item in cursor.description]
        return pd.DataFrame(rows, columns=columns)
    finally:
        connection.close()


def create_tab2(tab):
    latest_result = {"analysis_text": ""}

    def run_query():
        user_input = input_text.get("1.0", tk.END).strip()
        if not user_input:
            messagebox.showwarning("提醒", "請輸入查詢需求")
            return

        output_text.delete("1.0", tk.END)
        output_text.insert(tk.END, "正在建立安全查詢計畫...\n")
        tab.update()

        plan = None
        try:
            plan = generate_query_plan(user_input)
            sql, parameters, normalized_plan = build_select_query(
                plan, get_max_query_rows()
            )
            frame = execute_readonly_query(sql, parameters)
            result_text = (
                "查無資料"
                if frame.empty
                else frame.to_string(index=False)
            )
            latest_result["analysis_text"] = frame.to_csv(index=False)[
                : get_max_analysis_chars()
            ]
            write_audit_event(
                user_input,
                normalized_plan,
                "success",
                row_count=len(frame.index),
            )
            output_text.delete("1.0", tk.END)
            output_text.insert(
                tk.END,
                "安全查詢計畫：\n"
                + json.dumps(normalized_plan, ensure_ascii=False, indent=2)
                + "\n\n查詢結果：\n"
                + result_text,
            )
        except QueryPlanError as error:
            latest_result["analysis_text"] = ""
            write_audit_event(
                user_input,
                plan,
                "rejected",
                error_type=type(error).__name__,
            )
            output_text.delete("1.0", tk.END)
            output_text.insert(tk.END, f"查詢已拒絕：{error}")
        except Exception as error:
            latest_result["analysis_text"] = ""
            write_audit_event(
                user_input,
                plan,
                "failed",
                error_type=type(error).__name__,
            )
            output_text.delete("1.0", tk.END)
            output_text.insert(
                tk.END,
                f"查詢失敗：{type(error).__name__}",
            )

    def run_tech_analysis():
        data_text = latest_result["analysis_text"]
        if not data_text:
            messagebox.showwarning("提醒", "請先完成查詢後再分析")
            return
        output_text.insert(tk.END, "\n\n技術分析中...\n")
        tab.update()
        result = ask_gpt_about_stock(data_text)
        output_text.insert(tk.END, f"\n技術分析建議：\n{result}")

    tk.Label(tab, text="輸入唯讀查詢需求：").pack(anchor="w")
    input_text = scrolledtext.ScrolledText(tab, height=5, font=("Courier", 12))
    input_text.pack(fill="x", padx=10)

    button_frame = tk.Frame(tab)
    button_frame.pack(pady=10)
    tk.Button(
        button_frame,
        text="建立安全查詢並執行",
        command=run_query,
        width=22,
    ).pack(side="left", padx=5)
    tk.Button(
        button_frame,
        text="分析查詢結果",
        command=run_tech_analysis,
        width=18,
    ).pack(side="left", padx=5)

    tk.Label(tab, text="執行結果：").pack(anchor="w")
    output_text = scrolledtext.ScrolledText(
        tab, height=25, font=("Courier", 12)
    )
    output_text.pack(fill="both", expand=True, padx=10, pady=5)
