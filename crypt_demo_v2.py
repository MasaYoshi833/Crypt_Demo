# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 21:09:12 2025

@author: my199
"""

# app.py
# Y coin 取引 - Streamlitアプリ（フル実装）
#
# 特徴:
# - ユーザー名のみでログイン（パスワードなし）
# - 永続化はJSONファイル（data.json）
# - 表示単位: 円（Mock）, Y coin（単位表示付き）
# - 販売所（Dealer）: Fee 2% 表示、価格推移（2025-07-01 以降の初期履歴を生成）、
#   価格は「1.00 Ycoin = XXX 円（Mock）」形式
# - 取引所（Exchange）: 買い板（左）・売り板（右）→ 約定履歴 → 注文入力（自動マッチング）
# - 取引所 Fee 0.5%
# - Host アカウントでログインした場合のみ「取引履歴を全削除」ボタンが表示される
# - 画面構成：上段 販売所、下段 取引所（ご要望どおり上下配置）
#
# 使い方:
#  streamlit run app.py
#
# 必要: requirements.txt に `streamlit` と `pandas` を含めること
# （例）
# streamlit
# pandas
#

import streamlit as st
import json, os, random, time
from datetime import datetime, timedelta
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

DATA_FILE = "data.json"

# 設定
INITIAL_PRICE = 100.0  # 初期価格（円（Mock））
INITIAL_MOCK = 1000.0  # 初期付与（円（Mock））
INITIAL_Y = 0.0
DEALER_FEE_BPS = 200   # 2.0%
EX_FEE_BPS = 50        # 0.5%
DEALER_ALPHA = 0.05    # 価格調整係数（需給）
PRICE_HISTORY_START = datetime(2025, 7, 1, 0, 0, 0)

# -------------------------
# データ永続化
# -------------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},           # username -> {"mock":float, "y":float}
            "orders": [],          # list of orders dict
            "trades": [],          # list of trade dicts
            "price_history": []    # list of {"ts": epoch, "price": float}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# -------------------------
# ヘルパー
# -------------------------
def now_ts():
    return int(time.time())

def fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def decimal_str(x, ndigits=2):
    d = Decimal(str(x)).quantize(Decimal(10) ** -ndigits, rounding=ROUND_HALF_UP)
    return format(d, f"f")

def get_last_price():
    if data["price_history"]:
        return float(data["price_history"][-1]["price"])
    else:
        return float(INITIAL_PRICE)

def append_price(price, ts=None):
    if ts is None:
        ts = now_ts()
    data["price_history"].append({"ts": ts, "price": float(price)})
    # keep a reasonable limit
    if len(data["price_history"]) > 10000:
        data["price_history"] = data["price_history"][-10000:]
    save_data(data)

def ensure_price_history():
    # 初回起動時に 2025/7/1 以降の価格履歴を生成（1時間間隔のランダムウォークに類似）
    if data["price_history"]:
        return
    start = PRICE_HISTORY_START
    now = datetime.now()
    pts = []
    price = INITIAL_PRICE
    # step: 6-hour steps to avoid too many points (adjustable)
    step = timedelta(hours=6)
    cur = start
    # Seed randomness for reproducibility across runs if file absent during this session
    rand = random.Random(12345)
    while cur <= now:
        # small random fluctuation to simulate background trades
        noise = rand.uniform(-0.8, 0.8)
        price = max(0.01, price + noise)
        pts.append({"ts": int(cur.timestamp()), "price": float(round(price, 6))})
        cur += step
    data["price_history"] = pts
    # ensure last price exists at current time too
    append_price(price)
    save_data(data)

def init_app():
    ensure_price_history()
    save_data(data)

init_app()

# -------------------------
# Wallet & user management
# -------------------------
def user_exists(username):
    return username in data["users"]

def create_user(username):
    if user_exists(username):
        return False
    data["users"][username] = {"mock": float(INITIAL_MOCK), "y": float(INITIAL_Y)}
    save_data(data)
    return True

def get_wallet(username):
    u = data["users"].get(username)
    if not u:
        return 0.0, 0.0
    return float(u["mock"]), float(u["y"])

def set_wallet(username, mock, y):
    data["users"][username]["mock"] = float(mock)
    data["users"][username]["y"] = float(y)
    save_data(data)

# -------------------------
# Dealer (販売所) ロジック
# -------------------------
def dealer_buy(username, qty_y):
    """
    ユーザーが販売所で Y を購入する（円(Mock) -> Y）
    qty_y: 購入数量（Y）
    """
    price = get_last_price()
    cost = price * qty_y
    fee = cost * DEALER_FEE_BPS / 10000.0
    need = cost + fee
    mock, y = get_wallet(username)
    if mock + 1e-9 < need:
        return False, "円（Mock）残高不足です"
    # 決済
    set_wallet(username, mock - need, y + qty_y)
    ts = now_ts()
    # 記録（販売所は対手が Exchange/Dealer）
    data["trades"].append({
        "ts": ts,
        "venue": "dealer",
        "buyer": username,
        "seller": "Dealer",
        "price": float(price),
        "qty": float(qty_y),
        "fee_bps": DEALER_FEE_BPS,
        "fee_buyer": float(fee),
        "fee_seller": 0.0
    })
    # 価格調整（需給）
    newp = price + DEALER_ALPHA * qty_y + random.uniform(-0.1, 0.1)
    append_price(newp, ts)
    save_data(data)
    return True, f"{qty_y} Y coin を購入しました（価格 {decimal_str(price,4)} 円/1Y、手数料 {decimal_str(fee,2)} 円）"

def dealer_sell(username, qty_y):
    """
    ユーザーが販売所で Y を売る（Y -> 円(Mock)）
    """
    price = get_last_price()
    mock, y = get_wallet(username)
    if y + 1e-9 < qty_y:
        return False, "Y coin 残高不足です"
    proceeds = price * qty_y
    fee = proceeds * DEALER_FEE_BPS / 10000.0
    set_wallet(username, mock + (proceeds - fee), y - qty_y)
    ts = now_ts()
    data["trades"].append({
        "ts": ts,
        "venue": "dealer",
        "buyer": "Dealer",
        "seller": username,
        "price": float(price),
        "qty": float(qty_y),
        "fee_bps": DEALER_FEE_BPS,
        "fee_buyer": 0.0,
        "fee_seller": float(fee)
    })
    newp = max(0.01, price - DEALER_ALPHA * qty_y + random.uniform(-0.1, 0.1))
    append_price(newp, ts)
    save_data(data)
    return True, f"{qty_y} Y coin を売却しました（価格 {decimal_str(price,4)} 円/1Y、手数料 {decimal_str(fee,2)} 円）"

# -------------------------
# Orderbook / Exchange ロジック
# -------------------------
# Order structure: {"id": int, "user": str, "side": "buy"/"sell", "price": float, "qty": float, "ts": int}
def next_order_id():
    existing = [o.get("id",0) for o in data["orders"]]
    return max(existing)+1 if existing else 1

def place_order(user, side, price, qty):
    oid = next_order_id()
    entry = {"id": oid, "user": user, "side": side, "price": float(price), "qty": float(qty), "ts": now_ts()}
    data["orders"].append(entry)
    save_data(data)
    # try auto-match after placing
    matched = match_orders()  # will save data inside
    return oid, matched

def get_orderbook():
    buys = [o for o in data["orders"] if o["side"] == "buy" and o["qty"] > 0]
    sells = [o for o in data["orders"] if o["side"] == "sell" and o["qty"] > 0]
    # sort: buys desc price, then older first; sells asc price, older first
    buys.sort(key=lambda r: (-r["price"], r["ts"]))
    sells.sort(key=lambda r: (r["price"], r["ts"]))
    return buys, sells

def remove_filled_orders():
    data["orders"] = [o for o in data["orders"] if o["qty"] > 1e-12]
    save_data(data)

def match_orders():
    """
    自動マッチング:
    - 最良買いと最良売りがクロスする場合、約定
    - 約定価格は (buy_price + sell_price)/2
    - 手数料は双方とも Mock で徴収（0.5%）
    """
    changed = False
    while True:
        buys, sells = get_orderbook()
        if not buys or not sells:
            break
        best_buy = buys[0]
        best_sell = sells[0]
        if best_buy["price"] + 1e-9 < best_sell["price"]:
            break  # no cross
        trade_price = (best_buy["price"] + best_sell["price"]) / 2.0
        trade_qty = min(best_buy["qty"], best_sell["qty"])
        buy_user = best_buy["user"]
        sell_user = best_sell["user"]
        # check balances
        mb, yb = get_wallet(buy_user)
        ms, ys = get_wallet(sell_user)
        mock_cost = trade_price * trade_qty
        fee_buy = mock_cost * EX_FEE_BPS / 10000.0
        fee_sell = mock_cost * EX_FEE_BPS / 10000.0
        # buyer must have enough mock to cover cost+fee
        if mb + 1e-9 < (mock_cost + fee_buy):
            # remove buyer order (can't pay)
            # set its qty to 0 and continue
            for o in data["orders"]:
                if o["id"] == best_buy["id"]:
                    o["qty"] = 0.0
                    break
            remove_filled_orders()
            changed = True
            continue
        # seller must have enough Y
        if ys + 1e-9 < trade_qty:
            for o in data["orders"]:
                if o["id"] == best_sell["id"]:
                    o["qty"] = 0.0
                    break
            remove_filled_orders()
            changed = True
            continue
        # Settlement
        set_wallet(buy_user, mb - (mock_cost + fee_buy), yb + trade_qty)
        set_wallet(sell_user, ms + (mock_cost - fee_sell), ys - trade_qty)
        # record trade
        ts = now_ts()
        data["trades"].append({
            "ts": ts,
            "venue": "exchange",
            "buyer": buy_user,
            "seller": sell_user,
            "price": float(trade_price),
            "qty": float(trade_qty),
            "fee_bps": EX_FEE_BPS,
            "fee_buyer": float(fee_buy),
            "fee_seller": float(fee_sell)
        })
        # reduce order quantities
        for o in data["orders"]:
            if o["id"] == best_buy["id"]:
                o["qty"] = round(o["qty"] - trade_qty, 12)
            if o["id"] == best_sell["id"]:
                o["qty"] = round(o["qty"] - trade_qty, 12)
        # update price
        append_price(trade_price, ts)
        remove_filled_orders()
        changed = True
    if changed:
        save_data(data)
    return changed

# -------------------------
# Admin: Delete trades (Host only)
# -------------------------
def delete_all_trades(requesting_user):
    if requesting_user != "Host":
        return False, "権限がありません"
    # clear trades and orders
    data["trades"] = []
    data["orders"] = []
    save_data(data)
    return True, "全ての取引履歴と注文を削除しました（Hostによる実行）"

# -------------------------
# UI (Streamlit)
# -------------------------
st.set_page_config(page_title="Y coin 取引", layout="wide")
st.title("Y coin 取引")

# session
if "username" not in st.session_state:
    st.session_state.username = None

# simple login (username only)
st.sidebar.header("アカウント")
txt_user = st.sidebar.text_input("ユーザー名（半角）", value="" if st.session_state.username is None else st.session_state.username)
col_a, col_b = st.sidebar.columns([1,1])
with col_a:
    if st.sidebar.button("新規登録", key="signup", type="primary"):
        if not txt_user:
            st.sidebar.error("ユーザー名を入力してください")
        elif user_exists(txt_user):
            st.sidebar.error("ユーザー名は既に存在します")
        else:
            create_user(txt_user)
            st.session_state.username = txt_user
            st.sidebar.success(f"新規登録しました: {txt_user}")
            st.experimental_rerun()
with col_b:
    if st.sidebar.button("ログイン", key="login", type="secondary"):
        if not txt_user:
            st.sidebar.error("ユーザー名を入力してください")
        elif not user_exists(txt_user):
            st.sidebar.error("ユーザーが見つかりません（先に新規登録してください）")
        else:
            st.session_state.username = txt_user
            st.sidebar.success(f"ログインしました: {txt_user}")
            st.experimental_rerun()

if st.sidebar.button("ログアウト"):
    st.session_state.username = None
    st.experimental_rerun()

# Auto-refresh toggle and manual refresh button
auto_refresh = st.sidebar.checkbox("自動更新 (3秒)", value=True)
if auto_refresh:
    st.experimental_set_query_params(_r=int(time.time()))
    st.autorefresh(interval=3000, key="autorefresh")

# Must be logged in to see trading UI
if not st.session_state.username:
    st.info("ユーザー名でログインしてください（パスワード不要）。新規登録で初期ウォレット: 1000 円（Mock） が付与されます。")
    st.stop()

username = st.session_state.username

# Wallet display at top (always visible)
mock_bal, y_bal = get_wallet(username)
current_price = get_last_price()
y_value_in_mock = y_bal * current_price
total_value = mock_bal + y_value_in_mock

col1, col2, col3 = st.columns([2,2,2])
with col1:
    st.metric(label="円（Mock）残高", value=f"{decimal_str(mock_bal,2)} 円（Mock）")
with col2:
    st.metric(label="Y coin 残高", value=f"{decimal_str(y_bal,6)} Y coin")
with col3:
    st.metric(label="ポートフォリオ時価（合計）", value=f"{decimal_str(total_value,2)} 円（Mock）",
              delta=f"Y coin評価: {decimal_str(y_value_in_mock,2)} 円（Mock）")

st.markdown("---")

# --------------------------------
# DEALER (販売所) - 上部
# --------------------------------
st.header("販売所（Dealer） — 即時約定 / 手数料 **2%**")
st.markdown("**表示:** 1.00 Y coin = XXX 円（Mock） の形式で表示します")
# current price display in requested format
st.subheader(f"現在価格: 1.00 Y coin = {decimal_str(current_price,4)} 円（Mock）")

# Price chart (from price_history; after 2025-07-01)
st.subheader("価格推移（2025/07/01 以降）")
ph = pd.DataFrame(data["price_history"])
if not ph.empty:
    ph["time"] = pd.to_datetime(ph["ts"], unit='s')
    ph_plot = ph.set_index("time")["price"]
    st.line_chart(ph_plot)
else:
    st.write("価格履歴がありません。")

# Dealer trade history (latest 100)
st.subheader("販売所 取引履歴（最新）")
dealer_trades = [t for t in data["trades"] if t["venue"] == "dealer"]
if dealer_trades:
    df_dealer = pd.DataFrame([{
        "時刻": fmt_time(t["ts"]),
        "買い手": t["buyer"] if t["buyer"] else "-",
        "売り手": t["seller"] if t["seller"] else "-",
        "価格(円/1Y)": decimal_str(t["price"],4),
        "数量(Y)": decimal_str(t["qty"],6),
        "手数料(bps)": t.get("fee_bps", "")
    } for t in dealer_trades][::-1])
    st.dataframe(df_dealer)
else:
    st.write("販売所の取引はまだありません。")

# Dealer trading controls
st.subheader("販売所で取引する")
col_buy, col_sell = st.columns(2)
with col_buy:
    buy_qty = st.number_input("購入数量 (Y)", min_value=0.0, step=0.1, value=0.0, key="buy_qty")
    if st.button("販売所で購入（円→Y）"):
        if buy_qty <= 0:
            st.error("購入数量を入力してください")
        else:
            ok, msg = dealer_buy(username, buy_qty)
            if ok:
                st.success(msg)
                # refresh displayed values
                mock_bal, y_bal = get_wallet(username)
            else:
                st.error(msg)
with col_sell:
    sell_qty = st.number_input("売却数量 (Y)", min_value=0.0, step=0.1, value=0.0, key="sell_qty")
    if st.button("販売所で売却（Y→円）"):
        if sell_qty <= 0:
            st.error("売却数量を入力してください")
        else:
            ok, msg = dealer_sell(username, sell_qty)
            if ok:
                st.success(msg)
                mock_bal, y_bal = get_wallet(username)
            else:
                st.error(msg)

st.markdown("---")

# --------------------------------
# EXCHANGE (取引所) - 下部
# --------------------------------
st.header("取引所（Orderbook） — 手数料 **0.5%** / 自動マッチングあり")
st.markdown("買い板（左）・売り板（右） → 約定履歴 → 注文入力の順で表示します。")

# Orderbook display - buy left, sell right
st.subheader("板情報（Orderbook）")
buys, sells = get_orderbook()
col_buys, col_sells = st.columns(2)
with col_buys:
    st.markdown("**買い板（高い順）**")
    if buys:
        df_buys = pd.DataFrame([{
            "注文ID": o["id"],
            "ユーザー": o["user"],
            "価格(円/1Y)": decimal_str(o["price"],4),
            "数量残(Y)": decimal_str(o["qty"],6),
            "時刻": fmt_time(o["ts"])
        } for o in buys])
        st.dataframe(df_buys)
    else:
        st.write("買い注文なし")
with col_sells:
    st.markdown("**売り板（安い順）**")
    if sells:
        df_sells = pd.DataFrame([{
            "注文ID": o["id"],
            "ユーザー": o["user"],
            "価格(円/1Y)": decimal_str(o["price"],4),
            "数量残(Y)": decimal_str(o["qty"],6),
            "時刻": fmt_time(o["ts"])
        } for o in sells])
        st.dataframe(df_sells)
    else:
        st.write("売り注文なし")

# Exchange trades history
st.subheader("取引所 約定履歴（最新）")
ex_trades = [t for t in data["trades"] if t["venue"] == "exchange"]
if ex_trades:
    df_ex = pd.DataFrame([{
        "時刻": fmt_time(t["ts"]),
        "買い手": t["buyer"],
        "売り手": t["seller"],
        "価格(円/1Y)": decimal_str(t["price"],4),
        "数量(Y)": decimal_str(t["qty"],6),
        "手数料(bps)": t.get("fee_bps", EX_FEE_BPS)
    } for t in ex_trades][::-1])
    st.dataframe(df_ex)
else:
    st.write("取引所の約定はまだありません。")

st.markdown("----")

# Order placement (below history per request)
st.subheader("注文を出す / 自動マッチング")
col_side, col_price, col_qty = st.columns([1,1,1])
with col_side:
    side = st.selectbox("売買", ("買い", "売り"))
with col_price:
    o_price = st.number_input("希望価格 (円/1Y)", min_value=0.0001, step=0.1, value=float(current_price), key="order_price")
with col_qty:
    o_qty = st.number_input("数量 (Y)", min_value=0.0, step=0.1, value=1.0, key="order_qty")

if st.button("板に注文を出す"):
    if o_qty <= 0:
        st.error("数量を入力してください")
    else:
        # Pre-check: for sell, ensure user has Y; for buy, ensure rough mock availability
        mock_bal, y_bal = get_wallet(username)
        if side == "買い":
            need_est = o_price * o_qty * (1 + EX_FEE_BPS / 10000.0)
            if mock_bal + 1e-9 < need_est:
                st.warning("（目安）円（Mock）残高が不足の可能性があります。マッチング時の約定価格で最終的にチェックされます。")
            oid, matched = place_order(username, "buy", o_price, o_qty)
            st.success(f"買い注文を板に出しました（注文ID {oid}）")
            if matched:
                st.success("注文出し後に自動マッチングが実行され、約定が発生しました")
        else:
            if y_bal + 1e-9 < o_qty:
                st.error("Y coin 残高不足です。売り注文を出せません")
            else:
                oid, matched = place_order(username, "sell", o_price, o_qty)
                st.success(f"売り注文を板に出しました（注文ID {oid}）")
                if matched:
                    st.success("注文出し後に自動マッチングが実行され、約定が発生しました")

# Manual match button (in addition to auto-match on order placement)
if st.button("手動で板をマッチング（即時実行）"):
    changed = match_orders()
    if changed:
        st.success("マッチングを実行し、約定がありました")
    else:
        st.info("マッチング実行：約定なし")

st.markdown("---")

# Host-only: delete trades/orders
if username == "Host":
    st.warning("Host 権限: 取引履歴と未約定注文をすべて削除できます")
    if st.button("Delete: 全取引履歴と注文を削除する（Hostのみ）"):
        ok, msg = delete_all_trades(username)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

# small footer info
st.caption("注記: このアプリは学習用のシミュレーションです。実際の通貨や暗号資産への適用・資金の受け渡しは行いません。")
