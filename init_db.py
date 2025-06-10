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

if __name__ == "__main__":
    create_user_quota_table()
    print("user_quota 表已创建或已存在。")
