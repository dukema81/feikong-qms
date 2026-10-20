# -*- coding: utf-8 -*-
"""飞控QMS系统 · 数据层（零依赖：sqlite3 + WAL，24 张表）。"""
import os
import sqlite3
import threading

_TLS = threading.local()


def close_thread_conns():
    """兜底关闭当前线程登记的连接（防异常路径泄漏持锁）。"""
    for c in getattr(_TLS, "cons", []):
        try:
            c.close()
        except Exception:                                     # noqa: BLE001
            pass
    _TLS.cons = []

DB_PATH = os.environ.get("FEIKONG_DB") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "feikong.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS seq(name TEXT PRIMARY KEY, val INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL,
  dept TEXT DEFAULT '', enabled INTEGER DEFAULT 1, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  category TEXT DEFAULT '', contact TEXT DEFAULT '', phone TEXT DEFAULT '',
  grade TEXT DEFAULT 'B', score REAL DEFAULT 80, enabled INTEGER DEFAULT 1,
  remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS materials(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  spec TEXT DEFAULT '', unit TEXT DEFAULT '件', supplier TEXT DEFAULT '',
  critical INTEGER DEFAULT 0, key_character TEXT DEFAULT '', enabled INTEGER DEFAULT 1,
  remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS plans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  mat_code TEXT DEFAULT '', itype TEXT NOT NULL, aql TEXT DEFAULT '1.0',
  il TEXT DEFAULT 'II', sample_rule TEXT DEFAULT '一次抽样',
  critical_ac INTEGER DEFAULT 0, major_ac INTEGER DEFAULT 1, minor_ac INTEGER DEFAULT 2,
  enabled INTEGER DEFAULT 1, remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS plan_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, plan_code TEXT NOT NULL, seq INTEGER DEFAULT 1,
  item TEXT NOT NULL, standard TEXT DEFAULT '', tool TEXT DEFAULT '',
  severity TEXT DEFAULT 'B', sip TEXT DEFAULT '', method TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS defects(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  category TEXT NOT NULL, severity TEXT DEFAULT 'B',
  mat_code TEXT DEFAULT '', process TEXT DEFAULT '', enabled INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS inspections(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL, itype TEXT NOT NULL,
  mat_code TEXT DEFAULT '', mat_name TEXT DEFAULT '', supplier TEXT DEFAULT '',
  order_no TEXT DEFAULT '', process TEXT DEFAULT '', batch_no TEXT DEFAULT '',
  lot_size INTEGER DEFAULT 0, sample_size INTEGER DEFAULT 0, aql TEXT DEFAULT '1.0',
  status TEXT NOT NULL DEFAULT '待检验', inspector TEXT DEFAULT '',
  started TEXT DEFAULT '', finished TEXT DEFAULT '', result TEXT DEFAULT '',
  critical_bad INTEGER DEFAULT 0, major_bad INTEGER DEFAULT 0, minor_bad INTEGER DEFAULT 0,
  verdict TEXT DEFAULT '', disposition TEXT DEFAULT '',
  ncr_no TEXT DEFAULT '', judged_by TEXT DEFAULT '', created TEXT NOT NULL,
  creator TEXT NOT NULL, closed TEXT DEFAULT '', remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS inspection_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ins_no TEXT NOT NULL, seq INTEGER DEFAULT 1,
  item TEXT NOT NULL, standard TEXT DEFAULT '', tool TEXT DEFAULT '',
  severity TEXT DEFAULT 'B', value_text TEXT DEFAULT '',
  result TEXT DEFAULT '', bad_qty INTEGER DEFAULT 0, defect_code TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS ncrs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL, ins_no TEXT DEFAULT '',
  mat_code TEXT DEFAULT '', batch_no TEXT DEFAULT '', qty INTEGER DEFAULT 0,
  bad_qty INTEGER DEFAULT 0, severity TEXT DEFAULT 'B', description TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT '待评审', review TEXT DEFAULT '',
  disposition TEXT DEFAULT '', owner TEXT DEFAULT '', due TEXT DEFAULT '',
  verified TEXT DEFAULT '', verifier TEXT DEFAULT '', closed TEXT DEFAULT '',
  created TEXT NOT NULL, creator TEXT NOT NULL, cost REAL DEFAULT 0, remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS capas(
  id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE NOT NULL, source TEXT DEFAULT '内部',
  ncr_no TEXT DEFAULT '', problem TEXT NOT NULL, step TEXT DEFAULT 'D1',
  leader TEXT DEFAULT '', members TEXT DEFAULT '', description TEXT DEFAULT '',
  root_cause TEXT DEFAULT '', actions TEXT DEFAULT '', effect TEXT DEFAULT '',
  target TEXT DEFAULT '', status TEXT NOT NULL DEFAULT '进行中',
  due TEXT DEFAULT '', closed TEXT DEFAULT '', created TEXT NOT NULL,
  creator TEXT NOT NULL, remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS capa_tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, capa_no TEXT NOT NULL, phase TEXT DEFAULT 'D5',
  action TEXT NOT NULL, owner TEXT DEFAULT '', due TEXT DEFAULT '',
  status TEXT DEFAULT '待执行', done TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS scorings(
  id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL, supplier TEXT NOT NULL,
  lots INTEGER DEFAULT 0, accepted INTEGER DEFAULT 0, irr REAL DEFAULT 100,
  ppm REAL DEFAULT 0, q_score REAL DEFAULT 0, d_score REAL DEFAULT 0, r_score REAL DEFAULT 0,
  total REAL DEFAULT 0, grade TEXT DEFAULT 'B', created TEXT NOT NULL,
  UNIQUE(month, supplier));
CREATE TABLE IF NOT EXISTS coq(
  id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL, category TEXT NOT NULL,
  item TEXT NOT NULL, amount REAL DEFAULT 0, dept TEXT DEFAULT '', created TEXT NOT NULL,
  creator TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS spc_series(
  id INTEGER PRIMARY KEY AUTOINCREMENT, mat_code TEXT DEFAULT '', process TEXT NOT NULL,
  char_name TEXT NOT NULL, usl REAL, lsl REAL, target REAL,
  grp INTEGER DEFAULT 1, value REAL NOT NULL, operator TEXT DEFAULT '',
  sample_time TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS qdocs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  category TEXT DEFAULT 'SIP', version TEXT DEFAULT 'V1.0', owner TEXT DEFAULT '',
  status TEXT DEFAULT '编制中', released TEXT DEFAULT '',
  changed TEXT DEFAULT '', created TEXT NOT NULL, remark TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS api_keys(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, key_hash TEXT NOT NULL,
  prefix TEXT DEFAULT '', scope TEXT DEFAULT 'read', enabled INTEGER DEFAULT 1,
  created TEXT NOT NULL, last_used TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS webhooks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, url TEXT NOT NULL,
  secret TEXT NOT NULL, events TEXT DEFAULT '', enabled INTEGER DEFAULT 1,
  created TEXT NOT NULL, last_status TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS webhook_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, hook_id INTEGER NOT NULL, event TEXT NOT NULL,
  payload TEXT DEFAULT '', status TEXT DEFAULT 'pending', response TEXT DEFAULT '',
  ts TEXT NOT NULL, attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS field_maps(
  id INTEGER PRIMARY KEY AUTOINCREMENT, system TEXT NOT NULL, entity TEXT NOT NULL,
  ext_id TEXT NOT NULL, int_id TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, data TEXT DEFAULT '',
  ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idem_keys(
  key TEXT PRIMARY KEY, route TEXT NOT NULL, response TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, action TEXT NOT NULL,
  detail TEXT DEFAULT '', ip TEXT DEFAULT '', ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(
  code TEXT PRIMARY KEY, value TEXT NOT NULL, remark TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_ins_no ON inspections(no);
CREATE INDEX IF NOT EXISTS ix_ins_type ON inspections(itype, status);
CREATE INDEX IF NOT EXISTS ix_itm_ins ON inspection_items(ins_no);
CREATE INDEX IF NOT EXISTS ix_spc ON spc_series(process, char_name, grp);
"""

DEFAULT_SETTINGS = [
    ("aql_default", "1.0", "默认AQL接收质量限"),
    ("first_article_required", "1", "批量生产前首件必检"),
    ("ipqc_interval", "120", "过程巡检间隔（分钟）"),
    ("fqc_full_check", "0", "成品是否全检"),
    ("ncr_due_days", "7", "NCR处置默认时限（天）"),
    ("capa_due_days", "30", "CAPA默认关闭时限（天）"),
    ("concession_max", "0.03", "让步接收不良率上限"),
    ("critical_block", "1", "致命缺陷是否阻断放行"),
    ("spc_rule", "western_electric", "控制图判异规则集"),
    ("cpk_target", "1.33", "过程能力目标值"),
    ("supplier_grade_a", "90", "A级供应商分数线"),
    ("on_close_rate", "0.95", "NCR/CAPA按期关闭率目标"),
]


def connect():
    cn = sqlite3.connect(DB_PATH, timeout=20)
    cn.row_factory = sqlite3.Row
    cn.execute("PRAGMA journal_mode=WAL")
    cn.execute("PRAGMA busy_timeout=20000")
    cn.execute("PRAGMA foreign_keys=ON")
    if not hasattr(_TLS, "cons"):
        _TLS.cons = []
    _TLS.cons.append(cn)
    return cn


def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    cn = connect()
    cn.executescript(SCHEMA)
    for code, value, remark in DEFAULT_SETTINGS:
        cn.execute("INSERT OR IGNORE INTO settings(code,value,remark) VALUES(?,?,?)",
                   (code, value, remark))
    cn.commit()
    cn.close()
    print("飞控QMS 数据库就绪：%s" % DB_PATH)


if __name__ == "__main__":
    init()
