import sqlite3
import pandas as pd

# 1. 连接数据库
db_path = 'E:/New_folder/Work/MyProject/LLM_Trader/trader/sentiment.db'
conn = sqlite3.connect(db_path)

# 2. 查看有哪些表
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print(f"数据库中的表: {tables}")

# 3. 假设你的表名是 'stock_price_bars' (或者是上面打印出来的名字)
# 使用 Pandas 读取前 5 行 (Pandas 的 read_sql 支持 chunksize，也能处理大文件)
try:
    df = pd.read_sql_query("SELECT * FROM stock_price_bars LIMIT 10", conn)
    print("\n--- 前 10 行数据预览 ---")
    print(df)
    print("\n--- 数据列信息 ---")
    print(df.info())
except Exception as e:
    print(f"读取失败: {e}")

conn.close()