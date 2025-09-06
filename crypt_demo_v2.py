# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 21:09:12 2025

@author: my199
"""

import streamlit as st
import json
import os
import random
from datetime import datetime, timedelta
import pandas as pd

DATA_FILE = "crypto_sim_data.json"

# -------------------------
# データ管理
# -------------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "exchange_orders": [],
            "transactions": [],
            "price_history": [{"time": "2025-07-01 00:00:00", "price": 100}],
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# -------------------------
# 価格シミュレーション
# -------------------------
def update_price(data):
    last_price = data["price_history"][-1]["price"]
    # ランダムな小幅変動
    rand_factor = random.uniform(0.98, 1.02)
    new_price = last_price * rand_factor
    now = datetime.now()
    data["price_history"].append({"time": now.strftime("%Y-%m-%d %H:%M:%S"), "price": new_price})
    save_data(data)

# -------------------------
# 初期化
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

data = load_data()
update_price(data)

# -------------------------
# ログイン & 新規登録
# -------------------------
st.title("💹 Y coin 取引")

username = st.text_input("ユーザー名を入力してください")

col1, col2 = st.columns(2)
with col1:
    if st.button("新規登録", type="primary"):
        if username in data["users"]:
            st.error("既に存在するユーザー名です。")
        else:
            data["users"][username] = {
                "wallet": {"円（Mock）": 1000, "Ycoin": 0},
            }
            save_data(data)
            st.session_state.user = username
            st.success("新規登録成功！ウォレットが作成されました。")

with col2:
    if st.button("ログイン", type="secondary"):
        if username in data["users"]:
            st.session_state.user = username
            st.success("ログイン成功！")
        else:
            st.error("ユーザーが存在しません。")

# -------------------------
# ログイン後の画面
# -------------------------
if st.session_state.user:
    user = st.session_state.user
    wallet = data["users"][user]["wallet"]

    st.subheader(f"👤 ログイン中: {user}")

    # 現在の価格
    current_price = data["price_history"][-1]["price"]

    # 評価額計算
    total_value = wallet["円（Mock）"] + wallet["Ycoin"] * current_price

    st.metric("円（Mock）残高", f"{wallet['円（Mock）']:.2f} 円（Mock）")
    st.metric("Y coin 残高", f"{wallet['Ycoin']:.2f} Y coin")
    st.metric("合計評価額", f"{total_value:.2f} 円（Mock）")

    # -------------------------
    # 販売所
    # -------------------------
    st.header("🏪 販売所（手数料 2%）")

    st.write(f"現在の価格: 1.00 Ycoin = {current_price:.2f} 円（Mock）")

    # 履歴表示
    dealer_tx = [tx for tx in data["transactions"] if tx["place"] == "dealer"]
    st.subheader("📈 販売所の価格推移")
    df_price = pd.DataFrame(data["price_history"])
    df_price["time"] = pd.to_datetime(df_price["time"])
    df_price = df_price[df_price["time"] >= datetime(2025, 7, 1)]
    st.line_chart(df_price.set_index("time")["price"])

    st.subheader("📜 販売所の取引履歴")
    st.table(dealer_tx[-10:])

    # 取引フォーム
    st.subheader("💱 販売所で取引する")
    trade_amount = st.number_input("数量 (Ycoin)", min_value=0.0, step=1.0)

    colb1, colb2 = st.columns(2)
    with colb1:
        if st.button("購入（円→Ycoin）"):
            cost = trade_amount * current_price
            fee = cost * 0.02
            total = cost + fee
            if wallet["円（Mock）"] >= total:
                wallet["円（Mock）"] -= total
                wallet["Ycoin"] += trade_amount
                data["transactions"].append({
                    "type": "buy",
                    "user": user,
                    "amount": trade_amount,
                    "price": current_price,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "place": "dealer"
                })
                data["price_history"].append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "price": current_price * 1.01
                })
                save_data(data)
                st.success("購入しました！")

    with colb2:
        if st.button("売却（Ycoin→円）"):
            if wallet["Ycoin"] >= trade_amount:
                proceeds = trade_amount * current_price
                fee = proceeds * 0.02
                wallet["Ycoin"] -= trade_amount
                wallet["円（Mock）"] += proceeds - fee
                data["transactions"].append({
                    "type": "sell",
                    "user": user,
                    "amount": trade_amount,
                    "price": current_price,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "place": "dealer"
                })
                data["price_history"].append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "price": current_price * 0.99
                })
                save_data(data)
                st.success("売却しました！")

    # -------------------------
    # 取引所
    # -------------------------
    st.header("🏛️ 取引所（手数料 0.5%）")

    # 板表示
    buy_orders = [o for o in data["exchange_orders"] if o["type"] == "buy"]
    sell_orders = [o for o in data["exchange_orders"] if o["type"] == "sell"]

    col_ex1, col_ex2 = st.columns(2)
    with col_ex1:
        st.subheader("📝 買い注文板")
        st.table(buy_orders[-10:])
    with col_ex2:
        st.subheader("📝 売り注文板")
        st.table(sell_orders[-10:])

    st.subheader("📊 取引所の取引履歴")
    exchange_tx = [tx for tx in data["transactions"] if tx["place"] == "exchange"]
    st.table(exchange_tx[-10:])

    st.subheader("💱 取引所で注文する")
    order_type = st.selectbox("注文タイプ", ["買い", "売り"])
    order_amount = st.number_input("数量 (Ycoin)", min_value=0.0, step=1.0, key="ex_amount")
    order_price = st.number_input("希望価格 (Mock)", min_value=0.0, step=1.0, key="ex_price")

    if st.button("注文を出す"):
        order = {
            "user": user,
            "type": "buy" if order_type == "買い" else "sell",
            "amount": order_amount,
            "price": order_price,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        data["exchange_orders"].append(order)
        save_data(data)
        st.success("注文を出しました！")

    # 自動マッチング
    matched = []
    for buy in buy_orders:
        for sell in sell_orders:
            if buy["price"] >= sell["price"] and buy["amount"] > 0 and sell["amount"] > 0:
                qty = min(buy["amount"], sell["amount"])
                trade_price = (buy["price"] + sell["price"]) / 2
                fee = qty * trade_price * 0.005

                # 更新
                data["users"][buy["user"]]["wallet"]["円（Mock）"] -= qty * trade_price + fee
                data["users"][buy["user"]]["wallet"]["Ycoin"] += qty
                data["users"][sell["user"]]["wallet"]["円（Mock）"] += qty * trade_price - fee
                data["users"][sell["user"]]["wallet"]["Ycoin"] -= qty

                buy["amount"] -= qty
                sell["amount"] -= qty

                data["transactions"].append({
                    "type": "exchange",
                    "buyer": buy["user"],
                    "seller": sell["user"],
                    "amount": qty,
                    "price": trade_price,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "place": "exchange"
                })
                matched.append((buy, sell))

    data["exchange_orders"] = [o for o in data["exchange_orders"] if o["amount"] > 0]
    if matched:
        save_data(data)
        st.success(f"{len(matched)} 件の注文が約定しました！")

    # -------------------------
    # Host の管理機能
    # -------------------------
    if user == "Host":
        if st.button("🚨 全取引履歴を削除"):
            data["transactions"] = []
            data["exchange_orders"] = []
            save_data(data)
            st.warning("全取引履歴を削除しました。")
