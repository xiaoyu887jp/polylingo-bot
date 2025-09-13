import sqlite3

DATABASE = '/var/data/data.db'

def create_user_quota_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_quota (
            user_id TEXT PRIMARY KEY,
            quota INTEGER DEFAULT 2000
        )
    ''')
    conn.commit(); conn.close()

def create_group_settings_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS group_settings (
            group_id TEXT PRIMARY KEY,
            card_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit(); conn.close()

def create_usage_records_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS usage_records (
            group_id TEXT,
            user_id TEXT,
            month TEXT,
            usage INTEGER DEFAULT 0,
            PRIMARY KEY (group_id, user_id, month)
        )
    ''')
    conn.commit(); conn.close()

# 兼容：你原来的单数表（如果别处还在用，就保留）
def create_user_plan_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_plan (
            user_id TEXT PRIMARY KEY,
            allowed_group_count INTEGER DEFAULT 1,
            current_group_ids TEXT DEFAULT ''
        )
    ''')
    conn.commit(); conn.close()

# Webhook 使用的复数表（推荐今后都用这一张）
def create_user_plans_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_plans (
            user_id TEXT PRIMARY KEY,
            plan_type TEXT,
            max_groups INTEGER,
            subscription_id TEXT
        )
    ''')
    conn.commit(); conn.close()

# 绑定关系表（Webhook/绑定检查依赖）
def create_group_bindings_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS group_bindings (
            group_id TEXT PRIMARY KEY,
            owner_id TEXT
        )
    ''')
    # 常用查询加索引（按 owner_id 统计已绑定数量）
    cur.execute('CREATE INDEX IF NOT EXISTS idx_group_bindings_owner ON group_bindings(owner_id)')
    conn.commit(); conn.close()

# 套餐信息表（含有效期）
def create_groups_table():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            plan_type TEXT,
            plan_owner TEXT,
            plan_remaining INTEGER,
            expires_at TEXT   -- ISO 格式的到期时间
        )
    ''')
    # 兼容旧库：若无 expires_at 列则补充
    try:
        cur.execute("ALTER TABLE groups ADD COLUMN expires_at TEXT")
    except:
        pass
    # 常用查询加索引（可选）
    cur.execute('CREATE INDEX IF NOT EXISTS idx_groups_owner ON groups(plan_owner)')
    conn.commit(); conn.close()

if __name__ == "__main__":
    create_user_quota_table()
    create_group_settings_table()
    create_usage_records_table()
    create_user_plan_table()       # 兼容旧逻辑
    create_user_plans_table()      # Webhook 依赖
    create_group_bindings_table()  # Webhook/绑定检查依赖
    create_groups_table()          # 含 expires_at
    print("✅ 所有数据表已创建或已存在。")
