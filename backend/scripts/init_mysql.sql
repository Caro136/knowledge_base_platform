-- ============================================================
-- 知识库管理平台 - MySQL 初始化脚本
--
-- 用途：在宿主机"既有 MySQL 实例"上创建本项目所需数据库（不建表，
--       表结构由 `python -m app.seed` 按 ORM 元数据自动创建）。
--
-- 用法（使用你的 MySQL 管理员账号执行一次即可）：
--     mysql -h127.0.0.1 -P3306 -uroot -p < backend/scripts/init_mysql.sql
--
-- 脚本幂等，可重复执行。
-- ============================================================

CREATE DATABASE IF NOT EXISTS kb_platform
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

-- 可选：为项目创建独立账号（推荐生产使用，避免应用直连 root）。
-- 若不需要，跳过本节，并把 backend/.env 的 MYSQL_USER/MYSQL_PASSWORD 改为 root 账号。
CREATE USER IF NOT EXISTS 'kb'@'localhost' IDENTIFIED BY 'kb_pass_2026';
CREATE USER IF NOT EXISTS 'kb'@'%' IDENTIFIED BY 'kb_pass_2026';

GRANT ALL PRIVILEGES ON kb_platform.* TO 'kb'@'localhost';
GRANT ALL PRIVILEGES ON kb_platform.* TO 'kb'@'%';

FLUSH PRIVILEGES;

-- 校验
SELECT SCHEMA_NAME AS created_database
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'kb_platform';
