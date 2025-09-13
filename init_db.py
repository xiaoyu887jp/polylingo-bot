import sqlite3

DATABASE = '/var/data/data.db'

def create_user_quota_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_quota (
            user_id TEXT PRIMARY KEY,
            quota INTEGER DEFAULT 2000
        )
    ''')
    conn.commit()
    conn.close()

def create_group_settings_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_settings (
            group_id TEXT PRIMARY KEY,
            card_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def create_usage_records_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_records (
            group_id TEXT,
            user_id TEXT,
            month TEXT,
            usage INTEGER DEFAULT 0,
            PRIMARY KEY (group_id, user_id, month)
        )
    ''')
    conn.commit()
    conn.close()

# 新增的 user_plan 数据表
def create_user_plan_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_plan (
            user_id TEXT PRIMARY KEY,
            allowed_group_count INTEGER DEFAULT 1,
            current_group_ids TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

# 新增的 groups 数据表（套餐绑定 + 到期时间）
def create_groups_table():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            plan_type TEXT,
            plan_owner TEXT,
            plan_remaining INTEGER,
            expires_at TEXT   -- ISO 格式的到期时间
        )
    ''')
    # 兼容旧库：如果 groups 表已存在但没有 expires_at，则尝试新增
    try:
        cursor.execute("ALTER TABLE groups ADD COLUMN expires_at TEXT")
    except:
        pass
    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_user_quota_table()
    create_group_settings_table()
    create_usage_records_table()
    create_user_plan_table()
    create_groups_table()   # 新增调用
    print("✅ 所有数据表已创建或已存在。")
