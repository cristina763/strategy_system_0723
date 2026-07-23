import os


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_openai_client():
    from openai import OpenAI

    return OpenAI(api_key=_required_env("OPENAI_API_KEY"))


def get_db_connection():
    import pymssql

    return pymssql.connect(
        host=os.getenv("MSSQL_HOST", "127.0.0.1"),
        user=os.getenv("MSSQL_USER", "yunnn"),
        password=_required_env("MSSQL_PASSWORD"),
        database=os.getenv("MSSQL_DATABASE", "ncu_database2025"),
        charset=os.getenv("MSSQL_CHARSET", "utf8"),
    )
