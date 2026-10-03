import os

# 测试一律用 SQLite：必须在 import app.* （engine 创建）之前设置
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SEED_ON_EMPTY", "false")
