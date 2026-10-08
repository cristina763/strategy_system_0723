import os


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _bounded_int(name, default, minimum, maximum):
    value = int(os.getenv(name, str(default)))
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def get_openai_client():
    from openai import OpenAI

    return OpenAI(api_key=_required_env("OPENAI_API_KEY"))


def get_openai_model():
    return os.getenv("OPENAI_MODEL", "gpt-4")


def get_max_query_rows():
    return _bounded_int("MSSQL_MAX_QUERY_ROWS", 200, 1, 1000)


def get_max_analysis_chars():
    return _bounded_int("OPENAI_MAX_ANALYSIS_CHARS", 12000, 1000, 50000)


def get_db_connection():
    import pymssql

    timeout = _bounded_int("MSSQL_QUERY_TIMEOUT_SECONDS", 15, 1, 120)
    return pymssql.connect(
        host=os.getenv("MSSQL_HOST", "127.0.0.1"),
        user=_required_env("MSSQL_READONLY_USER"),
        password=_required_env("MSSQL_READONLY_PASSWORD"),
        database=os.getenv("MSSQL_DATABASE", "ncu_database2025"),
        charset=os.getenv("MSSQL_CHARSET", "utf8"),
        login_timeout=timeout,
        timeout=timeout,
        appname="stock-strategy-readonly",
    )
