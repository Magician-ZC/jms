"""
数据库迁移脚本
在现有数据库上添加 account_type 和网点信息字段
"""
import sqlite3
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "token_data" / "tokens.db"


def migrate():
    """执行迁移：添加 account_type 和网点信息字段"""
    if not DB_PATH.exists():
        print(f"[迁移] 数据库不存在: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # 获取现有字段
        cursor.execute("PRAGMA table_info(tokens)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # 迁移1: 添加 account_type 字段
        if 'account_type' not in columns:
            print("[迁移] 添加 account_type 字段...")
            cursor.execute("""
                ALTER TABLE tokens 
                ADD COLUMN account_type VARCHAR(20) DEFAULT 'AGENT'
            """)
            cursor.execute("""
                UPDATE tokens SET account_type = 'AGENT' WHERE account_type IS NULL
            """)
            print("[迁移] account_type 字段添加完成")
        else:
            print("[迁移] account_type 字段已存在")
        
        # 迁移2: 添加 network_code 字段
        if 'network_code' not in columns:
            print("[迁移] 添加 network_code 字段...")
            cursor.execute("""
                ALTER TABLE tokens 
                ADD COLUMN network_code VARCHAR(50)
            """)
            print("[迁移] network_code 字段添加完成")
        else:
            print("[迁移] network_code 字段已存在")
        
        # 迁移3: 添加 network_name 字段
        if 'network_name' not in columns:
            print("[迁移] 添加 network_name 字段...")
            cursor.execute("""
                ALTER TABLE tokens 
                ADD COLUMN network_name VARCHAR(100)
            """)
            print("[迁移] network_name 字段添加完成")
        else:
            print("[迁移] network_name 字段已存在")
        
        # 迁移4: 添加 network_id 字段
        if 'network_id' not in columns:
            print("[迁移] 添加 network_id 字段...")
            cursor.execute("""
                ALTER TABLE tokens 
                ADD COLUMN network_id INTEGER
            """)
            print("[迁移] network_id 字段添加完成")
        else:
            print("[迁移] network_id 字段已存在")
        
        conn.commit()
        print("[迁移] 所有迁移完成！")
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
