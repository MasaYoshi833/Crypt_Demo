# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 19:16:07 2025

@author: my199
"""

import streamlit as st
import pandas as pd
import sqlite3
import hashlib, os, time, secrets
from datetime import datetime
from typing import Optional, Tuple

DB = "simdex.db"

# ---------------------- DB LAYER ----------------------
def db_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    con = db_conn(); cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        pw_hash TEXT,
        salt TEXT
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallets(
        user_id INTEGER PRIMARY KEY,
        mock REAL NOT NULL DEFAULT 0,
        y REAL NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        side TEXT,           -- 'buy' or 'sell'
        price REAL,
        qty_rem REAL,
        ts INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER,
        venue TEXT,          -- 'dealer' or 'exchange'
        buyer_id INTEGER,
        seller_id INTEGER,
        price REAL,
        qty REAL,
        fee_bps INTEGER,
        fee_buyer_mock REAL,
        fee_seller_mock REAL,
        FOREIGN KEY(buyer_id) REFERENCES users(id),
        FOREIGN KEY(seller_id) REFERENCES users(id)
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS state(
        k TEXT PRIMARY KEY,
        v TEXT
    );""")
    # 初期価格（100 Mock / Y）
    cur.execute("INSERT OR IGNORE INTO state(k,v) VALUES ('last_price','100')")
    con.commit(); con.close()

def get_user_by_name(username:str)->Optional[Tuple[int,str]]:
    con = db_conn(); cur = con.cursor()
    cur.execute("SELECT id, pw_hash, salt FROM users WHERE username=?", (username,))
    r = cur.fetchone(); con.close()
    return r

def create_user(username:str, password:str)->int:
    salt = secrets.token_hex(8)
    pw_hash = hashlib.sha256((password+salt).encode()).hexdigest()
    con = db_conn(); cur = con.cursor()
    cur.execute("INSERT INTO users(username,pw_hash,salt) VALUES (?,?,?)", (username, pw_hash, salt))
    uid = cur.lastrowid
    # 初期配布：1000 Mock / 0 Y
    cur.execute("INSERT INTO wallets(user_id,mock,y) VALUES (?,?,?)", (uid, 1000.0, 0.0))
    con.commit(); con.close()
    return uid

def check_password(username:str, password:str)->Optional[int]:
    r = get_user_by_name(username)
    if not r: return None
    uid, pw_hash, salt = r[0], r[1], r[2]
    if hashlib.sha256((password+salt).encode()).hexdigest() == pw_hash:
        return uid
    return None

def get_wallet(uid:int):
    con = db_conn(); cur = con.cursor()
    cur.execute("SELECT mock,y FROM wallets WHERE user_id=?", (uid,))
    r=cur.fetchone(); con.close()
    return (r[0], r[1]) if r else (0.0,0.0)

def set_wallet(uid:int, mock:float, y:float):
    con=db_conn(); cur=con.cursor()
    cur.execute("UPDATE wallets SET mock=?, y=? WHERE user_id=?", (mock,y,uid))
    con.commit(); con.close()

def get_username(uid:int)->str:
    con=db_conn(); cur=con.cursor()
    cur.execute("SELECT username FROM users WHERE id=?", (uid,))
    r=cur.fetchone(); con.close()
    return r[0] if r else "unknown"

def get_price()->float:
    con=db_conn(); cur=con.cursor()
    cur.execute("SELECT v FROM state WHERE k='last_price'")
    v = cur.fetchone()
    con.close()
    return float(v[0]) if v else 100.0

def set_price(p:float):
    p = max(1.0, float(p))
    con=db_conn(); cur=con.cursor()
    cur.execute("INSERT OR REPLACE INTO state(k,v) VALUES ('last_price',?)", (str(p),))
    con.commit(); con.close()

def add_trade(ts:int, venue:str, buyer_id:Optional[int], seller_id:Optional[int],
              price:float, qty:float, fee_bps:int, fee_buyer:float, fee_seller:float):
    con=db_conn(); cur=con.cursor()
    cur.execute("""INSERT INTO trades(ts,venue,buyer_id,seller_id,price,qty,fee_bps,fee_buyer_mock,fee_seller_mock)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (ts,venue,buyer_id,seller_id,price,qty,fee_bps,fee_buyer,fee_seller))
    con.commit(); con.close()

def list_trades(venue:Optional[str]=None, limit:int=200):
    con=db_conn(); cur=con.cursor()
    if venue:
        cur.execute("""SELECT ts,venue,buyer_id,seller_id,price,qty,fee_bps FROM trades
                       WHERE venue=? ORDER BY ts DESC LIMIT ?""", (venue, limit))
    else:
        cur.execute("""SELECT ts,venue,buyer_id,seller_id,price,qty,fee_bps FROM trades
                       ORDER BY ts DESC LIMIT ?""", (limit,))
    rows = cur.fetchall(); con.close()
    return rows

def place_order(uid:int, side:str, price:float, qty:float):
    ts=int(time.time())
    con=db_conn(); cur=con.cursor()
    cur.execute("INSERT INTO orders(user_id,side,price,qty_rem,ts) VALUES(?,?,?,?,?)",
                (uid,side,price,qty,ts))
    con.commit(); con.close()

def list_orderbook():
    con=db_conn(); cur=con.cursor()
    cur.execute("""SELECT o.id, u.username, o.side, o.price, o.qty_rem, o.ts
                   FROM orders o JOIN users u ON o.user_id=u.id
                   WHERE o.qty_rem>0""")
    rows = cur.fetchall(); con.close()
    buy = [r for r in rows if r[2]=='buy']
    sell= [r for r in rows if r[2]=='sell']
    # 買いは高い順、売りは安い順
    buy.sort(key=lambda x: (-x[3], x[5]))
    sell.sort(key=lambda x: (x[3], x[5]))
    return buy, sell

def get_order(order_id:int):
    con=db_conn(); cur=con.cursor()
    cur.execute("SELECT id,user_id,side,price,qty_rem,ts FROM orders WHERE id=?", (order_id,))
    r=cur.fetchone(); con.close()
    return r

def update_order_qty(order_id:int, new_qty:float):
    con=db_conn(); cur=con.cursor()
    cur.execute("UPDATE orders SET qty_rem=? WHERE id=?", (new_qty, order_id))
    con.commit(); con.close()

def delete_order(order_id:int):
    con=db_conn(); cur=con.cursor()
    cur.execute("DELETE FROM orders WHERE id=?", (order_id,))
    con.commit(); con.close()

# ---------------------- BUSINESS LOGIC ----------------------
DEALER_FEE_BPS = 200   # 2.00%
EX_FEE_BPS     = 50    # 0.50%
DEALER_ALPHA   = 0.05  # 需給で価格調整: 新価格 = 直近 + α*(買数量-売数量)

def format_ts(ts:int)->str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def dealer_buy(uid:int, qty:float)->Tuple[bool,str]:
    """販売所で Y を買う（Mock -> Y）"""
    price = get_price()
    mock_cost = price * qty
    fee = mock_cost * DEALER_FEE_BPS / 10000.0
    need = mock_cost + fee
    m,y = get_wallet(uid)
    if m < need: return False, "Mock残高不足"
    # 決済
    set_wallet(uid, m - need, y + qty)
    add_trade(int(time.time()), 'dealer', uid, None, price, qty, DEALER_FEE_BPS, fee, 0.0)
    # 価格上方調整
    newp = price + DEALER_ALPHA * qty
    set_price(newp)
    return True, f"{qty} Y を購入 (価格 {price} Mock, 手数料 {fee:.2f} Mock)"

def dealer_sell(uid:int, qty:float)->Tuple[bool,str]:
    """販売所で Y を売る（Y -> Mock）"""
    price = get_price()
    m,y = get_wallet(uid)
    if y < qty: return False, "Y 残高不足"
    proceeds = price * qty
    fee = proceeds * DEALER_FEE_BPS / 10000.0
    set_wallet(uid, m + (proceeds - fee), y - qty)
    add_trade(int(time.time()), 'dealer', None, uid, price, qty, DEALER_FEE_BPS, 0.0, fee)
    # 価格下方調整
    newp = price - DEALER_ALPHA * qty
    set_price(newp)
    return True, f"{qty} Y を売却 (価格 {price} Mock, 手数料 {fee:.2f} Mock)"

def match_orders():
    """板の自動マッチング。成約ごとに残高と履歴を更新。"""
    changed = False
    while True:
        buy, sell = list_orderbook()
        if not buy or not sell: break
        best_buy = buy[0]   # (id, username, side, price, qty_rem, ts)
        best_sell= sell[0]
        if best_buy[3] < best_sell[3]: break  # 価格が交差しない
        # 約定価格：中間（シンプル）
        trade_price = round((best_buy[3] + best_sell[3]) / 2.0, 6)
        trade_qty   = min(best_buy[4], best_sell[4])

        # 両サイドのユーザーID取得
        ob = get_order(best_buy[0]);  # id,user_id,side,price,qty_rem,ts
        os = get_order(best_sell[0])
        buy_uid = ob[1]; sell_uid = os[1]

        # 残高チェックと決済（Mock/Yの移転 + 手数料0.5%）
        fee_rate = EX_FEE_BPS/10000.0
        mock_cost = trade_price * trade_qty
        fee_buy   = mock_cost * fee_rate
        fee_sell  = mock_cost * fee_rate

        mb,yb = get_wallet(buy_uid)
        ms,ys = get_wallet(sell_uid)

        # バイヤーは Mock が必要、セラーは Y が必要
        if mb < mock_cost + fee_buy or ys < trade_qty:
            # どちらか不足なら、該当注文は削除/縮小
            if mb < mock_cost + fee_buy:
                # 買い手の注文を削る
                update_order_qty(best_buy[0], 0); delete_order(best_buy[0])
            if ys < trade_qty:
                update_order_qty(best_sell[0], 0); delete_order(best_sell[0])
            continue

        # 決済
        set_wallet(buy_uid, mb - (mock_cost + fee_buy), yb + trade_qty)
        set_wallet(sell_uid, ms + (mock_cost - fee_sell), ys - trade_qty)

        # 注文数量更新
        update_order_qty(best_buy[0], ob[4] - trade_qty)
        update_order_qty(best_sell[0], os[4] - trade_qty)
        if ob[4] - trade_qty <= 0: delete_order(best_buy[0])
        if os[4] - trade_qty <= 0: delete_order(best_sell[0])

        # 約定記録 & 価格更新（取引所の最後の約定を参照値に）
        ts = int(time.time())
        add_trade(ts, 'exchange', buy_uid, sell_uid, trade_price, trade_qty, EX_FEE_BPS, fee_buy, fee_sell)
        set_price(trade_price)
        changed = True
    return changed

# ---------------------- UI HELPERS ----------------------
def ensure_logged_in():
    st.session_state.setdefault("uid", None)
    st.session_state.setdefault("username", None)

def login_ui():
    st.title("Mock & Y Coin Simulation")
    st.subheader("ログイン / 新規登録")
    with st.form("login"):
        u = st.text_input("ユーザー名（半角）")
        p = st.text_input("パスワード", type="password")
        colA, colB = st.columns(2)
        with colA:
            login_btn = st.form_submit_button("ログイン")
        with colB:
            signup_btn = st.form_submit_button("新規登録（初回1000 Mock配布）")
    if login_btn:
        uid = check_password(u, p)
        if uid:
            st.session_state.uid = uid
            st.session_state.username = u
            st.success("ログイン成功！")
            st.experimental_rerun()
        else:
            st.error("ユーザー名またはパスワードが違います")
    if signup_btn:
        if get_user_by_name(u):
            st.error("そのユーザー名は既に存在します")
        elif not u or not p:
            st.error("ユーザー名とパスワードを入力してください")
        else:
            uid = create_user(u, p)
            st.session_state.uid = uid
            st.session_state.username = u
            st.success("登録しました（1000 Mock 付与）")
            st.experimental_rerun()

def main_ui():
    st.set_page_config(page_title="Sim DEX", layout="wide")
    st.sidebar.markdown(f"**ログイン中:** {st.session_state.username}")
    if st.sidebar.button("ログアウト"):
        st.session_state.uid = None
        st.session_state.username = None
        st.experimental_rerun()

    # 3秒ごとにオートリフレッシュ（残高・板・価格を“常時更新”）
    st_autorefresh = st.sidebar.checkbox("自動更新（3秒）", value=True)
    if st_autorefresh:
        st.experimental_set_query_params(refresh=str(int(time.time())))
        st.experimental_rerun  # just set param; st_autorefresh below:
    st.experimental_data_editor  # no-op to silence lint

    st_autorefresh_key = st.experimental_get_query_params().get("refresh", ["0"])[0]
    st_autorefresh_counter = st.sidebar.empty()
    st_autorefresh_counter.text(f"last refresh key={st_autorefresh_key}")
    st_autorefresh_widget = st.autorefresh(interval=3000, key="auto") if st_autorefresh else None

    # 残高表示（常時DBから読む）
    mock_bal, y_bal = get_wallet(st.session_state.uid)
    st.sidebar.metric("Mock 残高", f"{mock_bal:.2f}")
    st.sidebar.metric("Y 残高", f"{y_bal:.6f}")

    # 左右 2 カラム
    left, right = st.columns(2)

    # ---------- 左：販売所 ----------
    with left:
        st.header("販売所（即時交換 / Fee 2%）")
        price = get_price()
        st.subheader(f"現在価格: {price:.6f} Mock / 1 Y")
        # 売買フォーム
        with st.form("dealer_buy"):
            buy_qty = st.number_input("購入数量 (Y)", min_value=0.0, step=1.0, value=0.0)
            buy_submit = st.form_submit_button("購入（Mock→Y）")
        if buy_submit and buy_qty > 0:
            ok, msg = dealer_buy(st.session_state.uid, buy_qty)
            st.success(msg) if ok else st.error(msg)

        with st.form("dealer_sell"):
            sell_qty = st.number_input("売却数量 (Y)", min_value=0.0, step=1.0, value=0.0, key="dsell")
            sell_submit = st.form_submit_button("売却（Y→Mock）")
        if sell_submit and sell_qty > 0:
            ok, msg = dealer_sell(st.session_state.uid, sell_qty)
            st.success(msg) if ok else st.error(msg)

        # 販売所の取引履歴と価格チャート
        st.subheader("販売所 取引履歴（誰⇄誰が見えるのは取引所側。販売所は相手=Exchange）")
        trades = list_trades('dealer', 200)
        if trades:
            df = pd.DataFrame([{
                "時刻": format_ts(r[0]),
                "種別": "買" if r[2] else "売",  # buyer_id exists -> 買
                "ユーザー": get_username(r[2]) if r[2] else get_username(r[3]) if r[3] else "-",
                "相手方": "Exchange",
                "価格": r[4],
                "数量": r[5],
                "手数料(bps)": r[6]
            } for r in trades])
            st.dataframe(df)
        else:
            st.info("まだ販売所の取引はありません。")

        # 価格推移（全体の取引の時系列から）
        st.subheader("価格推移（年月日時分秒）")
        all_tr = list_trades(None, 500)
        if all_tr:
            dfp = pd.DataFrame([{"time": format_ts(r[0]), "price": r[4]} for r in all_tr][::-1])
            st.line_chart(dfp.set_index("time"))
        else:
            st.write("まだ価格データがありません。")

    # ---------- 右：取引所（板） ----------
    with right:
        st.header("取引所（板 / Fee 0.5%）")

        # 新規注文フォーム
        with st.form("new_order"):
            side = st.selectbox("売買区分", ["買い", "売り"])
            price_in = st.number_input("価格 (Mock/1Y)", min_value=1.0, step=1.0, value=max(1.0, get_price()))
            qty_in = st.number_input("数量 (Y)", min_value=1.0, step=1.0, value=1.0, key="oqty")
            submit = st.form_submit_button("板に注文を出す")
        if submit:
            if side == "買い":
                # 必要Mock（上限価格×数量 + 手数料分）を目安に
                need = price_in * qty_in * (1 + EX_FEE_BPS/10000.0)
                mb, yb = get_wallet(st.session_state.uid)
                if mb < need:
                    st.error("（目安）Mock不足の可能性がありますが、板マッチングで実際の約定金額は変動します。")
                place_order(st.session_state.uid, 'buy', price_in, qty_in)
                st.success("買い注文を板に出しました")
            else:
                mb, yb = get_wallet(st.session_state.uid)
                if yb < qty_in:
                    st.error("Y 残高不足の可能性があります。")
                place_order(st.session_state.uid, 'sell', price_in, qty_in)
                st.success("売り注文を板に出しました")

        # マッチング（全ユーザー共通で一括処理）
        if st.button("板をマッチング/更新"):
            changed = match_orders()
            st.success("マッチングを実行しました" + ("（約定あり）" if changed else "（約定なし）"))

        # 現在の板
        buy, sell = list_orderbook()
        st.subheader("買い板（高い順）")
        if buy:
            dfb = pd.DataFrame([{
                "注文ID": r[0], "ユーザー": r[1], "価格": r[3], "数量残": r[4], "時刻": format_ts(r[5])
            } for r in buy])
            st.dataframe(dfb)
        else:
            st.write("買い板なし")

        st.subheader("売り板（安い順）")
        if sell:
            dfs = pd.DataFrame([{
                "注文ID": r[0], "ユーザー": r[1], "価格": r[3], "数量残": r[4], "時刻": format_ts(r[5])
            } for r in sell])
            st.dataframe(dfs)
        else:
            st.write("売り板なし")

        # 取引所の取引履歴（誰が誰に売ったか）
        st.subheader("取引所 取引履歴（誰→誰が分かる）")
        ex_tr = list_trades('exchange', 200)
        if ex_tr:
            dfex = pd.DataFrame([{
                "時刻": format_ts(r[0]),
                "買い手": get_username(r[2]) if r[2] else "-",
                "売り手": get_username(r[3]) if r[3] else "-",
                "価格": r[4],
                "数量": r[5],
                "手数料(bps)": r[6]
            } for r in ex_tr])
            st.dataframe(dfex)
        else:
            st.write("まだ取引所の約定はありません。")

# ---------------------- APP ENTRY ----------------------
init_db()
ensure_logged_in()

# 未ログインならログイン画面、ログイン済みなら取引画面へ遷移
if not st.session_state["uid"]:
    login_ui()
else:
    main_ui()
