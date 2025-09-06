# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 19:16:07 2025

@author: my199
"""

import streamlit as st
import pandas as pd
import random
import time

# 初期化
if "wallets" not in st.session_state:
    st.session_state.wallets = {}  # {username: {"mock": int, "ycoin": int}}
if "orderbook" not in st.session_state:
    st.session_state.orderbook = {"buy": [], "sell": []}  # 板情報
if "tx_history" not in st.session_state:
    st.session_state.tx_history = []  # [(time, type, user, counterparty, price, amount)]
if "price_history" not in st.session_state:
    st.session_state.price_history = pd.DataFrame({"time": [], "price": []})

# --- ウォレット作成 ---
st.sidebar.header("ウォレット")
username = st.sidebar.text_input("ユーザー名")
if st.sidebar.button("ウォレット作成"):
    if username and username not in st.session_state.wallets:
        st.session_state.wallets[username] = {"mock": 1000, "ycoin": 0}
        st.success(f"{username} のウォレットを作成しました（1000 Mock 配布）")
    elif username in st.session_state.wallets:
        st.warning("そのユーザー名は既に存在します")

# --- 残高表示 ---
if username in st.session_state.wallets:
    wallet = st.session_state.wallets[username]
    st.sidebar.write(f"Mock残高: {wallet['mock']}")
    st.sidebar.write(f"Ycoin残高: {wallet['ycoin']}")

# --- 販売所（交換所が提示するレートで即時交換） ---
st.header("販売所で交換（交換業者イメージ）")
if not st.session_state.price_history.empty:
    current_price = st.session_state.price_history["price"].iloc[-1]
else:
    current_price = 100
st.write(f"現在価格（1 Ycoinあたり）: {current_price} Mock")

col1, col2 = st.columns(2)
with col1:
    buy_amount = st.number_input("購入Ycoin数量", min_value=1, step=1, key="buy_amount")
    if st.button("購入する（Mock→Ycoin）"):
        cost = buy_amount * current_price
        if wallet["mock"] >= cost:
            wallet["mock"] -= cost
            wallet["ycoin"] += buy_amount
            st.session_state.tx_history.append(
                (time.strftime("%H:%M:%S"), "販売所買", username, "Exchange", current_price, buy_amount)
            )
            st.success(f"{buy_amount} Ycoin を購入しました")
        else:
            st.error("Mock残高不足です")
with col2:
    sell_amount = st.number_input("売却Ycoin数量", min_value=1, step=1, key="sell_amount")
    if st.button("売却する（Ycoin→Mock）"):
        if wallet["ycoin"] >= sell_amount:
            wallet["ycoin"] -= sell_amount
            wallet["mock"] += sell_amount * current_price
            st.session_state.tx_history.append(
                (time.strftime("%H:%M:%S"), "販売所売", username, "Exchange", current_price, sell_amount)
            )
            st.success(f"{sell_amount} Ycoin を売却しました")
        else:
            st.error("Ycoin残高不足です")

# --- 板情報（相対取引のマッチングはまだ簡略化） ---
st.header("板取引（ユーザー間注文）")
side = st.selectbox("売買区分", ["買い", "売り"])
order_price = st.number_input("価格 (Mock/Ycoin)", min_value=1, step=1)
order_amount = st.number_input("数量 (Ycoin)", min_value=1, step=1, key="order_amount")
if st.button("板に注文を出す"):
    st.session_state.orderbook["buy" if side == "買い" else "sell"].append(
        {"user": username, "price": order_price, "amount": order_amount}
    )
    st.success(f"{side}注文を板に出しました")

st.subheader("現在の板情報")
st.write("買い注文", pd.DataFrame(st.session_state.orderbook["buy"]))
st.write("売り注文", pd.DataFrame(st.session_state.orderbook["sell"]))

# --- 取引履歴 ---
st.header("取引履歴")
if st.session_state.tx_history:
    df_tx = pd.DataFrame(st.session_state.tx_history, columns=["時間", "種別", "ユーザー", "相手方", "価格", "数量"])
    st.dataframe(df_tx[::-1])
else:
    st.write("取引履歴はまだありません")

# --- 価格チャート ---
st.header("価格チャート")
last_price = current_price
new_price = last_price + random.randint(-5, 5)
new_price = max(1, new_price)
new_data = pd.DataFrame({"time": [time.strftime("%H:%M:%S")], "price": [new_price]})
st.session_state.price_history = pd.concat([st.session_state.price_history, new_data], ignore_index=True)
st.line_chart(st.session_state.price_history.set_index("time"))
