# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 19:53:32 2025

@author: my199
"""

# app.py
import streamlit as st
import sqlite3, time, secrets, hashlib
from datetime import datetime
import pandas as pd
import math

DB = "simsim.db"

# ---------------------------
# Database helpers
# ---------------------------
def conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    c = conn().cursor()
    # users table: id, username, pw_hash, salt
    c.execute("""CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    pw_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                )""")
    # wallets: user_id -> mock, y
    c.execute("""CREATE TABLE IF NOT EXISTS wallets (
                    user_id INTEGER PRIMARY KEY,
                    mock REAL NOT NULL DEFAULT 0,
                    y REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )""")
    # orders: id,user_id,side,bid_price,qty_rem,ts
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    side TEXT,    -- 'buy' or 'sell'
                    price REAL,
                    qty_rem REAL,
                    ts INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )""")
    # trades: id, ts, venue, buyer_id, seller_id, price, qty, fee_bps, fee_buyer_mock, fee_seller_mock
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER,
                    venue TEXT,
                    buyer_id INTEGER,
                    seller_id INTEGER,
                    price REAL,
                    qty REAL,
                    fee_bps INTEGER,
                    fee_buyer_mock REAL,
                    fee_seller_mock REAL
                )""")
    # state: key -> value (store last_price)
    c.execute("""CREATE TABLE IF NOT EXISTS state (
                    k TEXT PRIMARY KEY,
                    v TEXT
                )""")
    # price history
    c.execute("""CREATE TABLE IF NOT EXISTS price_history (
                    ts INTEGER PRIMARY KEY,
                    price REAL
                )""")
    # initialize price if missing
    c.execute("INSERT OR IGNORE INTO state(k,v) VALUES ('last_price','100')")
    # ensure a price_history point exists
    c.execute("SELECT COUNT(*) FROM price_history")
    if c.fetchone()[0] == 0:
        now = int(time.time())
        c.execute("INSERT OR REPLACE INTO price_history(ts,price) VALUES (?,?)", (now, 100.0))
    conn().commit()

# ---------------------------
# Auth & wallet management
# ---------------------------
def hash_pw(password, salt):
    return hashlib.sha256((password + salt).encode()).hexdigest()

def create_user(username, password):
    salt = secrets.token_hex(8)
    h = hash_pw(password, salt)
    cur = conn().cursor()
    try:
        cur.execute("INSERT INTO users(username,pw_hash,salt) VALUES (?,?,?)", (username, h, salt))
        uid = cur.lastrowid
        # initial wallet: 1000 Mock, 0 Y
        cur.execute("INSERT INTO wallets(user_id,mock,y) VALUES (?,?,?)", (uid, 1000.0, 0.0))
        conn().commit()
        return True, "登録成功"
    except Exception as e:
        return False, "登録失敗（ユーザー名が既に存在する可能性）"

def verify_user(username, password):
    cur = conn().cursor()
    cur.execute("SELECT id,pw_hash,salt FROM users WHERE username=?", (username,))
    r = cur.fetchone()
    if not r:
        return None
    uid, stored_hash, salt = r
    if hash_pw(password, salt) == stored_hash:
        return uid
    return None

def get_wallet(uid):
    cur = conn().cursor()
    cur.execute("SELECT mock,y FROM wallets WHERE user_id=?", (uid,))
    r = cur.fetchone()
    if r:
        return float(r[0]), float(r[1])
    return 0.0, 0.0

def set_wallet(uid, mock, y):
    cur = conn().cursor()
    cur.execute("UPDATE wallets SET mock=?, y=? WHERE user_id=?", (float(mock), float(y), uid))
    conn().commit()

def get_username(uid):
    cur = conn().cursor()
    cur.execute("SELECT username FROM users WHERE id=?", (uid,))
    r = cur.fetchone()
    return r[0] if r else "unknown"

# ---------------------------
# State: price
# ---------------------------
def get_price():
    cur = conn().cursor()
    cur.execute("SELECT v FROM state WHERE k='last_price'")
    r = cur.fetchone()
    return float(r[0]) if r else 100.0

def set_price(p):
    p = max(0.0001, float(p))
    cur = conn().cursor()
    cur.execute("INSERT OR REPLACE INTO state(k,v) VALUES ('last_price',?)", (str(p),))
    # add to price history
    now = int(time.time())
    cur.execute("INSERT OR REPLACE INTO price_history(ts,price) VALUES (?,?)", (now, p))
    conn().commit()

def get_price_history(limit=200):
    cur = conn().cursor()
    cur.execute("SELECT ts,price FROM price_history ORDER BY ts DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["ts","price"])
    if df.empty:
        return pd.DataFrame({"time":[],"price":[]})
    df['time'] = df['ts'].apply(lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S"))
    return df.sort_values("ts").reset_index(drop=True)[["time","price"]]

# ---------------------------
# Dealer (販売所) logic
# ---------------------------
DEALER_FEE_BPS = 200  # 2%
DEALER_ALPHA = 0.05   # 価格調整係数（需給）

def dealer_buy(uid, qty_y):
    """Mock -> Y : buyer buys qty_y Y at current price + fee"""
    price = get_price()
    cost = price * qty_y
    fee = cost * DEALER_FEE_BPS / 10000.0
    need = cost + fee
    mock, y = get_wallet(uid)
    if mock + 1e-9 < need:
        return False, "Mock残高不足"
    # update wallets
    set_wallet(uid, mock - need, y + qty_y)
    # record trade (buyer_id, seller_id=None)
    ts = int(time.time())
    cur = conn().cursor()
    cur.execute("""INSERT INTO trades(ts,venue,buyer_id,seller_id,price,qty,fee_bps,fee_buyer_mock,fee_seller_mock)
                   VALUES(?,?,?,?,?,?,?,?,?)""", (ts, 'dealer', uid, None, price, qty_y, DEALER_FEE_BPS, fee, 0.0))
    # price adjusts up by alpha * qty
    newp = price + DEALER_ALPHA * qty_y
    set_price(newp)
    conn().commit()
    return True, f"購入: {qty_y} Y @ {price:.4f} (fee {fee:.4f} Mock)"

def dealer_sell(uid, qty_y):
    """Y -> Mock"""
    price = get_price()
    mock, y = get_wallet(uid)
    if y + 1e-9 < qty_y:
        return False, "Y残高不足"
    proceeds = price * qty_y
    fee = proceeds * DEALER_FEE_BPS / 10000.0
    # credit mock minus fee
    set_wallet(uid, mock + (proceeds - fee), y - qty_y)
    ts = int(time.time())
    cur = conn().cursor()
    cur.execute("""INSERT INTO trades(ts,venue,buyer_id,seller_id,price,qty,fee_bps,fee_buyer_mock,fee_seller_mock)
                   VALUES(?,?,?,?,?,?,?,?,?)""", (ts, 'dealer', None, uid, price, qty_y, DEALER_FEE_BPS, 0.0, fee))
    # price adjusts down
    newp = price - DEALER_ALPHA * qty_y
    set_price(max(0.0001, newp))
    conn().commit()
    return True, f"売却: {qty_y} Y @ {price:.4f} (fee {fee:.4f} Mock)"

# ---------------------------
# Orderbook & matching (取引所)
# ---------------------------
EX_FEE_BPS = 50  # 0.5%

def place_order(uid, side, price, qty):
    ts = int(time.time())
    cur = conn().cursor()
    cur.execute("INSERT INTO orders(user_id,side,price,qty_rem,ts) VALUES(?,?,?,?,?)", (uid, side, float(price), float(qty), ts))
    conn().commit()

def list_orderbook():
    cur = conn().cursor()
    cur.execute("""SELECT o.id, o.user_id, u.username, o.side, o.price, o.qty_rem, o.ts
                   FROM orders o JOIN users u ON o.user_id=u.id
                   WHERE o.qty_rem>0""")
    rows = cur.fetchall()
    buy = [r for r in rows if r[3]=='buy']
    sell= [r for r in rows if r[3]=='sell']
    buy.sort(key=lambda r: (-r[4], r[6]))   # 高い価格優先
    sell.sort(key=lambda r: (r[4], r[6]))   # 安い価格優先
    return buy, sell

def get_order(order_id):
    cur = conn().cursor()
    cur.execute("SELECT id,user_id,side,price,qty_rem,ts FROM orders WHERE id=?", (order_id,))
    return cur.fetchone()

def update_order_qty(order_id, new_qty):
    cur = conn().cursor()
    cur.execute("UPDATE orders SET qty_rem=? WHERE id=?", (float(new_qty), order_id))
    conn().commit()

def delete_order(order_id):
    cur = conn().cursor()
    cur.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn().commit()

def match_orders():
    """自動マッチング。買い板の最良と売り板の最良を突き合わせる。"""
    changed = False
    while True:
        buy, sell = list_orderbook()
        if not buy or not sell:
            break
        best_buy = buy[0]
        best_sell= sell[0]
        # best_buy: (id, user_id, username, 'buy', price, qty_rem, ts)
        if best_buy[4] < best_sell[4]:
            break  # no cross
        # trade price: midpoint
        trade_price = (best_buy[4] + best_sell[4]) / 2.0
        trade_qty = min(best_buy[5], best_sell[5])
        buy_order = get_order(best_buy[0])
        sell_order = get_order(best_sell[0])
        buy_uid = buy_order[1]; sell_uid = sell_order[1]
        # check balances
        mb, yb = get_wallet(buy_uid)
        ms, ys = get_wallet(sell_uid)
        mock_cost = trade_price * trade_qty
        fee_buy = mock_cost * EX_FEE_BPS / 10000.0
        fee_sell = mock_cost * EX_FEE_BPS / 10000.0
        if mb + 1e-9 < (mock_cost + fee_buy):
            # buyer insufficient -> delete buyer order
            delete_order(buy_order[0])
            continue
        if ys + 1e-9 < trade_qty:
            # seller insufficient -> delete seller order
            delete_order(sell_order[0])
            continue
        # execute settlement
        set_wallet(buy_uid, mb - (mock_cost + fee_buy), yb + trade_qty)
        set_wallet(sell_uid, ms + (mock_cost - fee_sell), ys - trade_qty)
        # update quantities
        new_bqty = buy_order[4] - trade_qty
        new_sqty = sell_order[4] - trade_qty
        update_order_qty(buy_order[0], new_bqty)
        update_order_qty(sell_order[0], new_sqty)
        if new_bqty <= 0:
            delete_order(buy_order[0])
        if new_sqty <= 0:
            delete_order(sell_order[0])
        # record trade
        ts = int(time.time())
        cur = conn().cursor()
        cur.execute("""INSERT INTO trades(ts,venue,buyer_id,seller_id,price,qty,fee_bps,fee_buyer_mock,fee_seller_mock)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (ts,'exchange', buy_uid, sell_uid, trade_price, trade_qty, EX_FEE_BPS, fee_buy, fee_sell))
        # update last price
        set_price(trade_price)
        conn().commit()
        changed = True
    return changed

def list_trades(venue=None, limit=200):
    cur = conn().cursor()
    if venue:
        cur.execute("SELECT ts,venue,buyer_id,seller_id,price,qty,fee_bps FROM trades WHERE venue=? ORDER BY ts DESC LIMIT ?", (venue, limit))
    else:
        cur.execute("SELECT ts,venue,buyer_id,seller_id,price,qty,fee_bps FROM trades ORDER BY ts DESC LIMIT ?", (limit,))
    return cur.fetchall()

# ---------------------------
# UI
# ---------------------------
init_db()
st.set_page_config(page_title="Sim DEX Simulator", layout="wide")
st.title("Sim DEX — Mock & Ycoin シミュレータ")

# session state
if "uid" not in st.session_state:
    st.session_state.uid = None
if "username" not in st.session_state:
    st.session_state.username = None

# ---------------------------
# Login / Signup
# ---------------------------
if st.session_state.uid is None:
    st.subheader("ログインまたは新規登録")
    with st.form("auth_form"):
        col1, col2 = st.columns([2,2])
        with col1:
            username = st.text_input("ユーザー名", key="auth_user")
        with col2:
            password = st.text_input("パスワード", type="password", key="auth_pw")
        c1, c2 = st.columns(2)
        signup = c1.form_submit_button("新規登録 (Register)", type="primary")
        login  = c2.form_submit_button("ログイン (Login)", type="secondary")

    if signup:
        if not username or not password:
            st.error("ユーザー名とパスワードを入力してください")
        else:
            ok, msg = create_user(username, password)
            if ok:
                st.success(msg + " — ログインしてください")
            else:
                st.error(msg)
    if login:
        if not username or not password:
            st.error("ユーザー名とパスワードを入力してください")
        else:
            uid = verify_user(username, password)
            if uid:
                st.session_state.uid = uid
                st.session_state.username = username
                st.experimental_rerun()
            else:
                st.error("認証失敗：ユーザー名またはパスワードが間違っています")
    st.stop()

# ---------------------------
# Main trading UI (logged in)
# ---------------------------
# auto-refresh toggle
autorefresh = st.sidebar.checkbox("自動更新 (3s)", value=True)
if autorefresh:
    st.experimental_set_query_params(_refresh=int(time.time()))
    st.experimental_rerun() if False else None  # noop; use st.autorefresh below

st.sidebar.write(f"ログイン中: **{st.session_state.username}**")
uid = st.session_state.uid
mock_bal, y_bal = get_wallet(uid)
st.sidebar.metric("Mock 残高", f"{mock_bal:.2f}")
st.sidebar.metric("Y 残高", f"{y_bal:.6f}")

# auto refresh 3s (this reruns the app; keep after showing sidebar)
if autorefresh:
    st.experimental_rerun if False else None  # avoid duplicate calls
    st.autorefresh(interval=3000, key="autorefresh")

left, right = st.columns(2)

# LEFT: Dealer / Sales (販売所)
with left:
    st.header("🏦 販売所 (Dealer) — Fee 2%")
    cur_price = get_price()
    st.subheader(f"現在価格: {cur_price:.6f} Mock / Y")
    st.write("※販売所は即時約定、需給（購入/売却数量）に応じて価格が動きます。")
    # buy Y with Mock
    with st.form("dealer_buy_form"):
        buy_qty = st.number_input("購入 Y 数量", min_value=0.0, step=1.0, value=0.0, key="dbuy")
        buy_btn = st.form_submit_button("購入 (Mock -> Y)")
    if buy_btn and buy_qty > 0:
        ok, msg = dealer_buy(uid, buy_qty)
        if ok:
            st.success(msg)
        else:
            st.error(msg)
    # sell Y for Mock
    with st.form("dealer_sell_form"):
        sell_qty = st.number_input("売却 Y 数量", min_value=0.0, step=1.0, value=0.0, key="dsell")
        sell_btn = st.form_submit_button("売却 (Y -> Mock)")
    if sell_btn and sell_qty > 0:
        ok, msg = dealer_sell(uid, sell_qty)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    # Dealer trade history
    st.subheader("販売所 取引履歴 (最新)")
    dealer_tr = list_trades('dealer', 200)
    if dealer_tr:
        df = pd.DataFrame([{
            "時刻": datetime.fromtimestamp(r[0]).strftime("%Y-%m-%d %H:%M:%S"),
            "種別": ("買" if r[2] else "売"),
            "ユーザー": get_username(r[2]) if r[2] else (get_username(r[3]) if r[3] else "-"),
            "価格": r[4],
            "数量": r[5],
            "手数料(bps)": r[6]
        } for r in dealer_tr])
        st.dataframe(df)
    else:
        st.write("販売所の取引はまだありません。")

    # price chart
    st.subheader("価格推移 (price history)")
    ph = get_price_history(500)
    if not ph.empty:
        ph_plot = ph.copy()
        ph_plot.index = pd.to_datetime(ph_plot['time'])
        st.line_chart(ph_plot['price'])
    else:
        st.write("まだ価格履歴がありません。")

# RIGHT: Exchange / Orderbook (取引所)
with right:
    st.header("📈 取引所 (Orderbook) — Fee 0.5%")
    st.write("板（注文）を出してマッチングしてください。")
    # new order form
    with st.form("new_order_form"):
        side = st.selectbox("売買", ("買い", "売り"))
        price_in = st.number_input("価格 (Mock / 1 Y)", min_value=0.0001, step=0.1, value=max(0.0001, get_price()), key="o_price")
        qty_in = st.number_input("数量 (Y)", min_value=0.0, step=1.0, value=1.0, key="o_qty")
        submit_order = st.form_submit_button("板に注文を出す")
    if submit_order and qty_in > 0:
        if side == "買い":
            # simple check: ensure buyer has at least price*qty*(1+fee)
            mock_need = price_in * qty_in * (1 + EX_FEE_BPS/10000.0)
            mb, yb = get_wallet(uid)
            if mb + 1e-9 < mock_need:
                st.warning("警告: 概算でMock残高が不足する可能性があります（ただしマッチング時の約定価格で決まります）。")
            place_order(uid, 'buy', price_in, qty_in)
            st.success("買い注文を板に出しました。")
        else:
            mb, yb = get_wallet(uid)
            if yb + 1e-9 < qty_in:
                st.error("Y残高不足です。注文を出せません。")
            else:
                place_order(uid, 'sell', price_in, qty_in)
                st.success("売り注文を板に出しました。")

    # manual match button
    if st.button("板をマッチング（最新の注文と約定）"):
        changed = match_orders()
        if changed:
            st.success("マッチング完了：約定あり")
        else:
            st.info("マッチング実行：約定なし")

    # show orderbook
    buy, sell = list_orderbook()
    st.subheader("買い板（高い順）")
    if buy:
        df_buy = pd.DataFrame([{"注文ID":r[0], "ユーザー":r[2], "価格":r[4], "数量残":r[5], "時刻": datetime.fromtimestamp(r[6]).strftime("%Y-%m-%d %H:%M:%S")} for r in buy])
        st.dataframe(df_buy)
    else:
        st.write("買い注文なし")

    st.subheader("売り板（安い順）")
    if sell:
        df_sell = pd.DataFrame([{"注文ID":r[0], "ユーザー":r[2], "価格":r[4], "数量残":r[5], "時刻": datetime.fromtimestamp(r[6]).strftime("%Y-%m-%d %H:%M:%S")} for r in sell])
        st.dataframe(df_sell)
    else:
        st.write("売り注文なし")

    # exchange trades (who->who)
    st.subheader("取引所 約定履歴 (誰が誰に) 最新")
    ex_tr = list_trades('exchange', 200)
    if ex_tr:
        dfex = pd.DataFrame([{
            "時刻": datetime.fromtimestamp(r[0]).strftime("%Y-%m-%d %H:%M:%S"),
            "買い手": get_username(r[2]) if r[2] else "-",
            "売り手": get_username(r[3]) if r[3] else "-",
            "価格": r[4],
            "数量": r[5],
            "手数料(bps)": r[6]
        } for r in ex_tr])
        st.dataframe(dfex)
    else:
        st.write("取引所の約定はまだありません。")

# footer: logout
st.sidebar.markdown("---")
if st.sidebar.button("ログアウト"):
    st.session_state.uid = None
    st.session_state.username = None
    st.experimental_rerun()
