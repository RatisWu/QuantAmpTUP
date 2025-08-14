import pymysql

# MySQL 連線設定
MYSQL_HOST = 'localhost'
MYSQL_USER = 'QuantAmpTUP'      # 修改成你的 MySQL 使用者
MYSQL_PASSWORD = 'CCDismyBOSS'  # 修改成你的密碼
DB_NAME = 'QuantAmpTUP'

# 建立連線
conn = pymysql.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    charset='utf8mb4',
    autocommit=True,
)
cursor = conn.cursor()

# 建立資料庫
cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
cursor.execute(f"USE {DB_NAME};")

# 建立 users 表
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

# 建立 instruments 表
cursor.execute("""
CREATE TABLE IF NOT EXISTS instruments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    instrument_name VARCHAR(50) NOT NULL,
    ip_address VARCHAR(50) NOT NULL UNIQUE,
    user_id INT NULL,
    occupied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
""")

# 建立 experiments 表
cursor.execute("""
CREATE TABLE IF NOT EXISTS experiments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    experiment_name VARCHAR(100),
    toml_path VARCHAR(255) NOT NULL,
    output_path VARCHAR(255) DEFAULT NULL,
    status ENUM('pending','running','done') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_status (user_id, status)
);
""")

print("資料庫與表格建立完成！")
cursor.close()
conn.close()

