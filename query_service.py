import hashlib
import json
import os
from datetime import datetime, timezone


TABLE_NAME = "trading_stock_test"
ALLOWED_COLUMNS = (
    "Date",
    "StockCode",
    "Capacity",
    "Volume",
    "Open",
    "High",
    "Low",
    "Close",
    "Change",
    "Transaction",
    "MA5",
    "MA10",
    "MA20",
    "MA60",
    "MA120",
    "MA240",
    "K_value",
    "D_value",
)
ALLOWED_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "LIKE"}
ALLOWED_DIRECTIONS = {"ASC", "DESC"}
ALLOWED_PLAN_KEYS = {"operation", "columns", "filters", "order_by", "limit"}


class QueryPlanError(ValueError):
    pass


def _validate_column(column):
    if column not in ALLOWED_COLUMNS:
        raise QueryPlanError(f"不允許的欄位：{column}")
    return column


def validate_query_plan(plan, max_rows=200):
    if not isinstance(plan, dict):
        raise QueryPlanError("查詢計畫必須是 JSON object")

    unknown_keys = set(plan) - ALLOWED_PLAN_KEYS
    if unknown_keys:
        raise QueryPlanError(f"查詢計畫包含不允許的欄位：{', '.join(sorted(unknown_keys))}")

    operation = str(plan.get("operation", "")).lower()
    if operation != "select":
        raise QueryPlanError("只允許唯讀 SELECT 查詢")

    columns = plan.get("columns") or ["Date", "StockCode", "Close", "Volume"]
    if not isinstance(columns, list) or not columns:
        raise QueryPlanError("columns 必須是非空陣列")
    if len(columns) > len(ALLOWED_COLUMNS):
        raise QueryPlanError("查詢欄位數量超過限制")
    columns = list(dict.fromkeys(_validate_column(column) for column in columns))

    filters = plan.get("filters") or []
    if not isinstance(filters, list) or len(filters) > 12:
        raise QueryPlanError("filters 必須是最多 12 筆的陣列")

    normalized_filters = []
    for item in filters:
        if not isinstance(item, dict):
            raise QueryPlanError("每個 filter 必須是 JSON object")
        if set(item) != {"column", "operator", "value"}:
            raise QueryPlanError("filter 只能包含 column、operator、value")
        column = _validate_column(item["column"])
        operator = str(item["operator"]).upper()
        if operator not in ALLOWED_OPERATORS:
            raise QueryPlanError(f"不允許的運算子：{operator}")
        value = item["value"]
        if value is None or isinstance(value, (dict, list, tuple, set, bool)):
            raise QueryPlanError("filter value 必須是字串或數字")
        normalized_filters.append(
            {"column": column, "operator": operator, "value": value}
        )

    order_by = plan.get("order_by") or []
    if not isinstance(order_by, list) or len(order_by) > 3:
        raise QueryPlanError("order_by 必須是最多 3 筆的陣列")

    normalized_order = []
    for item in order_by:
        if not isinstance(item, dict):
            raise QueryPlanError("每個 order_by 必須是 JSON object")
        if set(item) != {"column", "direction"}:
            raise QueryPlanError("order_by 只能包含 column、direction")
        column = _validate_column(item["column"])
        direction = str(item["direction"]).upper()
        if direction not in ALLOWED_DIRECTIONS:
            raise QueryPlanError(f"不允許的排序方向：{direction}")
        normalized_order.append({"column": column, "direction": direction})

    limit = plan.get("limit", min(100, max_rows))
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise QueryPlanError("limit 必須是整數")
    if limit < 1 or limit > max_rows:
        raise QueryPlanError(f"limit 必須介於 1 與 {max_rows} 之間")

    return {
        "operation": "select",
        "columns": columns,
        "filters": normalized_filters,
        "order_by": normalized_order,
        "limit": limit,
    }


def build_select_query(plan, max_rows=200):
    normalized = validate_query_plan(plan, max_rows)
    selected_columns = ", ".join(f"[{column}]" for column in normalized["columns"])
    sql = (
        f"SELECT TOP ({normalized['limit']}) {selected_columns} "
        f"FROM [{TABLE_NAME}]"
    )
    parameters = []

    conditions = []
    for item in normalized["filters"]:
        column_expression = (
            "CAST([Date] AS DATE)"
            if item["column"] == "Date"
            else f"[{item['column']}]"
        )
        conditions.append(f"{column_expression} {item['operator']} %s")
        parameters.append(item["value"])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    if normalized["order_by"]:
        clauses = [
            f"[{item['column']}] {item['direction']}"
            for item in normalized["order_by"]
        ]
        sql += " ORDER BY " + ", ".join(clauses)

    return sql, parameters, normalized


def write_audit_event(prompt, plan, status, row_count=None, error_type=None):
    path = os.getenv("QUERY_AUDIT_LOG", "query_audit.log")
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "plan": plan,
        "status": status,
        "row_count": row_count,
        "error_type": error_type,
    }
    try:
        with open(path, "a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass
