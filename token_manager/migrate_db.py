"""
数据库迁移脚本
在现有数据库上添加 account_type 字段
"""
import sqlite3
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "token_data" / "tokens.db"


def migrate():
    """执行迁移：添加 account_type 字段"""
    if not DB_PATH.exists():
        print(f"[迁移] 数据库不存在: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # 检查 account_type 字段是否已存在
        cursor.execute("PRAGMA table_info(tokens)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'account_type' in columns:
            print("[迁移] account_type 字段已存在，无需迁移")
            return True
        
        # 添加 account_type 字段，默认值为 'AGENT'
        print("[迁移] 添加 account_type 字段...")
        cursor.execute("""
            ALTER TABLE tokens 
            ADD COLUMN account_type VARCHAR(20) DEFAULT 'AGENT'
        """)
        
        # 更新现有记录的默认值
        cursor.execute("""
            UPDATE tokens SET account_type = 'AGENT' WHERE account_type IS NULL
        """)
        
        conn.commit()
        print("[迁移] 迁移完成！现有记录已设置为代理区(AGENT)类型")
        return True
        
    except Exception as e:
        print(f"[迁移] 迁移失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def check_db_structure():
    """检查数据库结构"""
    if not DB_PATH.exists():
        print(f"[检查] 数据库不存在: {DB_PATH}")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(tokens)")
        columns = cursor.fetchall()
        
        print("\n[数据库结构] tokens 表字段:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]}), nullable={col[3]==0}, default={col[4]}")
        
        # 查看现有数据
        cursor.execute("SELECT id, user_id, account, account_type, status FROM tokens")
        rows = cursor.fetchall()
        
        print(f"\n[数据] 现有 {len(rows)} 条记录:")
        for row in rows:
            print(f"  - id={row[0]}, user_id={row[1]}, account={row[2]}, type={row[3]}, status={row[4]}")
            
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check_db_structure()
    else:
        migrate()
        check_db_structure()
