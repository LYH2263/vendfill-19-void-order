import os

# app.database 在导入时即按 DATABASE_URL 建引擎，测试统一用 sqlite
os.environ.setdefault("DATABASE_URL", "sqlite://")
