import unittest

from query_service import QueryPlanError, build_select_query, validate_query_plan


class QueryServiceTests(unittest.TestCase):
    def test_builds_parameterized_select(self):
        plan = {
            "operation": "select",
            "columns": ["Date", "Close"],
            "filters": [
                {"column": "StockCode", "operator": "=", "value": "2330"}
            ],
            "order_by": [{"column": "Date", "direction": "DESC"}],
            "limit": 20,
        }

        sql, parameters, normalized = build_select_query(plan, 200)

        self.assertEqual(parameters, ["2330"])
        self.assertIn("SELECT TOP (20) [Date], [Close]", sql)
        self.assertIn("[StockCode] = %s", sql)
        self.assertIn("ORDER BY [Date] DESC", sql)
        self.assertEqual(normalized["operation"], "select")

    def test_rejects_write_operation(self):
        with self.assertRaises(QueryPlanError):
            validate_query_plan(
                {
                    "operation": "delete",
                    "columns": ["Date"],
                    "filters": [],
                    "order_by": [],
                    "limit": 10,
                }
            )

    def test_rejects_raw_sql(self):
        with self.assertRaises(QueryPlanError):
            validate_query_plan(
                {
                    "operation": "select",
                    "columns": ["Date"],
                    "filters": [],
                    "order_by": [],
                    "limit": 10,
                    "sql": "SELECT * FROM trading_stock_test; DELETE FROM trading_stock_test",
                }
            )

    def test_rejects_unknown_column(self):
        with self.assertRaises(QueryPlanError):
            validate_query_plan(
                {
                    "operation": "select",
                    "columns": ["Password"],
                    "filters": [],
                    "order_by": [],
                    "limit": 10,
                }
            )

    def test_rejects_limit_over_cap(self):
        with self.assertRaises(QueryPlanError):
            validate_query_plan(
                {
                    "operation": "select",
                    "columns": ["Date"],
                    "filters": [],
                    "order_by": [],
                    "limit": 201,
                },
                200,
            )

    def test_parameterizes_injection_value(self):
        plan = {
            "operation": "select",
            "columns": ["Date"],
            "filters": [
                {
                    "column": "StockCode",
                    "operator": "=",
                    "value": "2330'; DELETE FROM trading_stock_test; --",
                }
            ],
            "order_by": [],
            "limit": 10,
        }

        sql, parameters, _ = build_select_query(plan, 200)

        self.assertNotIn("DELETE", sql)
        self.assertEqual(
            parameters,
            ["2330'; DELETE FROM trading_stock_test; --"],
        )


if __name__ == "__main__":
    unittest.main()
