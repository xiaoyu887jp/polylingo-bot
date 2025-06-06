import sqlite3

DATABASE = 'data.db'

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

if __name__ == "__main__":
    create_group_settings_table()
    print("group_settings 表已创建或已存在。")

