# -*- coding: utf-8 -*-
"""
Created on Sat Sep  6 21:36:02 2025

@author: my199
"""

import streamlit as st
import random
import datetime
import matplotlib.pyplot as plt
import pandas as pd

st.set_page_config(page_title="Y coin 取引", layout="wide")

# ----------------------
# 初期化
# ----------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "wallet" not in st.session_state:
    st.session_state.wallet = {"Ycoin": 5.0, "JPY": 10000.0}
if "price_history" not in st.session_state:
    base_date = datetime.date(2025, 7, 1)
    st.session_state.price_history = [
        (base_date + datetime.timedelta(days=i), 1000 + random.randint(-100, 100))
        for i in range(10)
    ]
if "market_price" not in st.session_state:
    st.session_state.market_price = st.session_state.price_history[-1][1]
if "exchange_orders" not in st.session_state:
    st.session_state.exchange_orders = {"buy": [], "sell": []}
if "trade_history" not in st.session_state:
    st.session_state.trade_history = []

# ダミーユーザー
dummy_users = ["UserA", "UserB", "UserC"]

# ----------------------
# 価格のランダム変動
# ----------------------
def update_price():
    last_price = st.session_state.market_price
    # 激しい乱高下
    change = random.randint(-100, 100)
    new_price = max(100, last_price + change)
    st.session_state.market_price = new_price
    st.session_state.price_history.append((datetime.date.today(), new_price))
    if len(st.session_state.price_history) > 100:
        st.session_state.price_history.pop(0)

# ----------------------
# ダミーユーザー取引生成
# ----------------------
def simulate_dummy_trades():
    if random.random() < 0.5:  # 50%の確率で売買
        user = random.choice(dummy_users)
        side = random.choice(["buy", "sell"])
        amount = round(random.uniform(0.1, 1.0), 2)
        price = st.session_state.market_price
        fee_rate = 0.02 if random.random() < 0.5 else 0.005
        st.session_state.trade_history.insert(
            0,
            {
                "user": user,
                "side": side,
                "amount": amount,
                "price": price,
                "fee": fee_rate,
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "place": "販売所" if fee_rate == 0.02 else "取引所",
            },
        )
        if len(st.session_state.trade_history) > 10:
            st.session_state.trade_history.pop()

# ----------------------
# 売買実行（販売所・取引所共通）
# ----------------------
def execute_trade(user, side, amount, place):
    price = st.session_state.market_price
    if place == "販売所":
        fee_rate = 0.02
    else:
        fee_rate = 0.005

    if side == "buy":
        cost = price * amount * (1 + fee_rate)
        if st.session_state.wallet["JPY"] >= cost:
            st.session_state.wallet["JPY"] -= cost
            st.session_state.wallet["Ycoin"] += amount
            st.session_state.trade_history.insert(
                0,
                {
                    "user": user,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "fee": fee_rate,
                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "place": place,
                },
            )
    elif side == "sell":
        if st.session_state.wallet["Ycoin"] >= amount:
            revenue = price * amount * (1 - fee_rate)
            st.session_state.wallet["JPY"] += revenue
            st.session_state.wallet["Ycoin"] -= amount
            st.session_state.trade_history.insert(
                0,
                {
                    "user": user,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "fee": fee_rate,
                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "place": place,
                },
            )
    if len(st.session_state.trade_history) > 10:
        st.session_state.trade_history.pop()

# ----------------------
# ログイン
# ----------------------
if not st.session_state.user:
    st.title("Y coin 取引")
    username = st.text_input("ユーザー名を入力してください")
    if st.button("ログイン") and username:
        st.session_state.user = username
        st.rerun()
else:
    st.title("Y coin 取引")
    st.write(f"👤 ユーザー名: {st.session_state.user}")

    # ----------------------
    # ウォレット表示
    # ----------------------
    wallet = st.session_state.wallet
    market_value = wallet["Ycoin"] * st.session_state.market_price + wallet["JPY"]
    st.subheader("ウォレット")
    st.write(f"Y coin 残高: {wallet['Ycoin']:.2f} Ycoin")
    st.write(f"円残高: {wallet['JPY']:.2f} 円(Mock)")
    st.write(f"合計: {market_value:.2f} 円(Mock)")

    # ----------------------
    # レイアウト（PCは左右分割 / モバイルは上下配置）
    # ----------------------
    if st.columns(2)[0]._width < 400:  # 簡易的にモバイル判定
        layout_mode = "mobile"
    else:
        layout_mode = "pc"

    if layout_mode == "pc":
        col1, col2 = st.columns(2)
    else:
        col1 = st.container()
        col2 = st.container()

    # ----------------------
    # 販売所
    # ----------------------
    with col1:
        st.subheader("販売所（手数料 2%）")

        # 価格推移
        update_price()
        dates, prices = zip(*st.session_state.price_history)
        fig, ax = plt.subplots()
        ax.plot(dates, prices, marker="o")
        ax.set_title("Ycoin 価格推移")
        ax.set_ylabel("円(Mock)")
        st.pyplot(fig)

        # 現在価格
        st.write(f"現在価格: 1.00 Ycoin = {st.session_state.market_price:.2f} 円(Mock)")

        # 履歴
        st.write("取引履歴（直近10件）")
        df = pd.DataFrame(st.session_state.trade_history)
        if not df.empty:
            st.dataframe(df.head(10))

        # 売買
        st.write("取引")
        side = st.radio("売買選択", ["buy", "sell"], horizontal=True)
        amount = st.number_input("数量 (Ycoin)", min_value=0.01, step=0.01)
        if st.button("販売所で実行"):
            execute_trade(st.session_state.user, side, amount, "販売所")

    # ----------------------
    # 取引所
    # ----------------------
    with col2:
        st.subheader("取引所（手数料 0.5%）")

        # 板
        st.write("買い板 / 売り板（ダミー）")
        st.write("（自動マッチング中）")

        # 履歴
        st.write("取引履歴（直近10件）")
        df = pd.DataFrame(st.session_state.trade_history)
        if not df.empty:
            st.dataframe(df.head(10))

        # 売買
        st.write("取引")
        side = st.radio("売買選択", ["buy", "sell"], horizontal=True, key="ex_side")
        amount = st.number_input("数量 (Ycoin)", min_value=0.01, step=0.01, key="ex_amt")
        if st.button("取引所で実行"):
            execute_trade(st.session_state.user, side, amount, "取引所")

    # ----------------------
    # ダミートレード更新
    # ----------------------
    simulate_dummy_trades()

    # ----------------------
    # Hostユーザー用：履歴削除
    # ----------------------
    if st.session_state.user == "Host":
        if st.button("取引履歴を全削除"):
            st.session_state.trade_history = []
            st.success("取引履歴を削除しました")

    # ----------------------
    # 自動更新（1秒ごと）
    # ----------------------
    st.experimental_autorefresh(interval=1000, key="refresh")
