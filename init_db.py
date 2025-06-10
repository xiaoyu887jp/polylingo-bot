import sqlite3

DATABASE = 'data.db'

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

if __name__ == "__main__":
    create_user_quota_table()
    create_group_settings_table()
    create_usage_records_table()
    print("✅ 所有数据表已创建或已存在。")
