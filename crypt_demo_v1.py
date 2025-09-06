# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 19:53:32 2025

@author: my199
"""

# app.py
import streamlit as st
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt

DATA_FILE = "crypto_sim_data.json"

# -------------------------
# データ管理
# -------------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "exchange_orders": [], "transactions": [], "price": 100}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# -------------------------
# 初期化
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

data = load_data()

# -------------------------
# ログイン & 新規登録
# -------------------------
st.title("🪙 Mock & Ycoin 取引シミュレーション")

username = st.text_input("ユーザー名")
password = st.text_input("パスワード", type="password")

col1, col2 = st.columns(2)
with col1:
    if st.button("新規登録", type="primary"):
        if username in data["users"]:
            st.error("既に存在するユーザー名です。")
        else:
            data["users"][username] = {
                "password": password,
                "wallet": {"Mock": 1000, "Ycoin": 0},
            }
            save_data(data)
            st.session_state.user = username
            st.success("新規登録成功！ウォレットが作成されました。")

with col2:
    if st.button("ログイン", type="secondary"):
        if username in data["users"] and data["users"][username]["password"] == password:
            st.session_state.user = username
            st.success("ログイン成功！")
        else:
            st.error("ユーザー名またはパスワードが間違っています。")

# -------------------------
# ログイン後の画面
# -------------------------
if st.session_state.user:
    user = st.session_state.user
    wallet = data["users"][user]["wallet"]

    st.subheader(f"👤 ログイン中: {user}")
    st.metric("Mock残高", f"{wallet['Mock']:.2f}")
    st.metric("Ycoin残高", f"{wallet['Ycoin']:.2f}")

    col_left, col_right = st.columns(2)

    # -------------------------
    # 販売所
    # -------------------------
    with col_left:
        st.header("🏪 販売所")

        current_price = data["price"]
        st.write(f"現在の販売所価格: **{current_price:.2f} Mock / Ycoin**")
        trade_amount = st.number_input("購入/売却量 (Ycoin)", min_value=0.0, step=1.0)

        if st.button("販売所で購入"):
            cost = trade_amount * current_price
            fee = cost * 0.02
            total = cost + fee
            if wallet["Mock"] >= total:
                wallet["Mock"] -= total
                wallet["Ycoin"] += trade_amount
                data["transactions"].append({
                    "type": "buy",
                    "user": user,
                    "amount": trade_amount,
                    "price": current_price,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "place": "dealer"
                })
                data["price"] *= 1.01  # 需給による価格上昇
                save_data(data)
                st.success("購入しました！")

        if st.button("販売所で売却"):
            if wallet["Ycoin"] >= trade_amount:
                proceeds = trade_amount * current_price
                fee = proceeds * 0.02
                wallet["Ycoin"] -= trade_amount
                wallet["Mock"] += proceeds - fee
                data["transactions"].append({
                    "type": "sell",
                    "user": user,
                    "amount": trade_amount,
                    "price": current_price,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "place": "dealer"
                })
                data["price"] *= 0.99  # 需給による価格下落
                save_data(data)
                st.success("売却しました！")

        st.subheader("📈 販売所の取引履歴")
        dealer_tx = [tx for tx in data["transactions"] if tx["place"] == "dealer"]
        st.table(dealer_tx[-10:])

        # 価格推移チャート
        if dealer_tx:
            times = [tx["time"] for tx in dealer_tx]
            prices = [tx["price"] for tx in dealer_tx]
            fig, ax = plt.subplots()
            ax.plot(times, prices, marker="o")
            ax.set_xticklabels(times, rotation=45, ha="right")
            ax.set_ylabel("Price (Mock)")
            st.pyplot(fig)

    # -------------------------
    # 取引所
    # -------------------------
    with col_right:
        st.header("🏛️ 取引所（板取引）")

        order_type = st.selectbox("注文タイプ", ["買い", "売り"])
        order_amount = st.number_input("数量 (Ycoin)", min_value=0.0, step=1.0)
        order_price = st.number_input("希望価格 (Mock)", min_value=0.0, step=1.0)

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

        # 板情報の表示
        buy_orders = [o for o in data["exchange_orders"] if o["type"] == "buy"]
        sell_orders = [o for o in data["exchange_orders"] if o["type"] == "sell"]

        st.subheader("📝 買い注文板")
        st.table(buy_orders[-10:])
        st.subheader("📝 売り注文板")
        st.table(sell_orders[-10:])

        # 簡易マッチング（同価格帯があれば約定）
        matched = []
        for buy in buy_orders:
            for sell in sell_orders:
                if buy["price"] >= sell["price"] and buy["amount"] > 0 and sell["amount"] > 0:
                    qty = min(buy["amount"], sell["amount"])
                    trade_price = (buy["price"] + sell["price"]) / 2
                    fee = qty * trade_price * 0.005

                    # 更新
                    data["users"][buy["user"]]["wallet"]["Mock"] -= qty * trade_price + fee
                    data["users"][buy["user"]]["wallet"]["Ycoin"] += qty
                    data["users"][sell["user"]]["wallet"]["Mock"] += qty * trade_price - fee
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

        # 完了した注文を削除
        data["exchange_orders"] = [o for o in data["exchange_orders"] if o["amount"] > 0]
        if matched:
            save_data(data)
            st.success(f"{len(matched)} 件の注文が約定しました！")

        st.subheader("📊 取引所の取引履歴")
        exchange_tx = [tx for tx in data["transactions"] if tx["place"] == "exchange"]
        st.table(exchange_tx[-10:])

