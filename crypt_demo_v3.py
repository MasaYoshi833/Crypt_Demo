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
if "wallets" not in st.session_state:
    st.session_state.wallets = {}
if "price_history" not in st.session_state:
    base_date = datetime.date(2025, 7, 1)
    st.session_state.price_history = [
        (base_date + datetime.timedelta(days=i), 100 + random.randint(-10, 10))
        for i in range(10)
    ]
if "market_price" not in st.session_state:
    st.session_state.market_price = st.session_state.price_history[-1][1]
if "trade_history" not in st.session_state:
    st.session_state.trade_history = []

dummy_users = ["UserA", "UserB", "UserC"]

# ----------------------
# 価格更新（ボラティリティを抑制）
# ----------------------
def update_price():
    last_price = st.session_state.market_price
    change = random.randint(-50, 150)  # 乱高下はこの範囲
    new_price = max(10, last_price + change)
    st.session_state.market_price = new_price
    st.session_state.price_history.append((datetime.date.today(), new_price))
    if len(st.session_state.price_history) > 100:
        st.session_state.price_history.pop(0)

# ----------------------
# ダミートレード
# ----------------------
def simulate_dummy_trades():
    if random.random() < 0.5:
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
# トレード実行
# ----------------------
def execute_trade(user, side, amount, place):
    price = st.session_state.market_price
    fee_rate = 0.02 if place == "販売所" else 0.005
    wallet = st.session_state.wallets[user]

    if side == "buy":
        cost = price * amount * (1 + fee_rate)
        if wallet["JPY"] >= cost:
            wallet["JPY"] -= cost
            wallet["Ycoin"] += amount
            st.session_state.trade_history.insert(
                0,
                {"user": user, "side": side, "amount": amount, "price": price,
                 "fee": fee_rate, "time": datetime.datetime.now().strftime("%H:%M:%S"),
                 "place": place}
            )
    elif side == "sell":
        if wallet["Ycoin"] >= amount:
            revenue = price * amount * (1 - fee_rate)
            wallet["JPY"] += revenue
            wallet["Ycoin"] -= amount
            st.session_state.trade_history.insert(
                0,
                {"user": user, "side": side, "amount": amount, "price": price,
                 "fee": fee_rate, "time": datetime.datetime.now().strftime("%H:%M:%S"),
                 "place": place}
            )
    if len(st.session_state.trade_history) > 10:
        st.session_state.trade_history.pop()

# ----------------------
# ログイン画面
# ----------------------
if not st.session_state.user:
    st.title("Y coin 取引")

    col1, _ = st.columns([1, 3])
    with col1:
        username = st.text_input("ユーザー名", max_chars=20)

    if st.button("ログイン") and username:
        if username not in st.session_state.wallets:
            st.warning("新規登録してください")
        else:
            st.session_state.user = username
            st.rerun()

    if st.button("新規登録") and username:
        if username in st.session_state.wallets:
            st.warning("既に登録済みです")
        else:
            st.session_state.wallets[username] = {"Ycoin": 0.0, "JPY": 1000.0}
            st.session_state.user = username
            st.success(f"{username} を新規登録しました（1000円(Mock)を付与）")
            st.rerun()

else:
    st.title("Y coin 取引")
    user = st.session_state.user
    wallet = st.session_state.wallets[user]

    st.write(f"👤 ユーザー名: {user}")

    # ----------------------
    # ウォレット表示（元のスタイルに復帰）
    # ----------------------
    st.markdown("### 💰 ウォレット")
    market_value = wallet["Ycoin"] * st.session_state.market_price + wallet["JPY"]
    st.write(f"Y coin 残高: **{wallet['Ycoin']:.2f} Ycoin**")
    st.write(f"円残高: **{wallet['JPY']:.2f} 円(Mock)**")
    st.write(f"合計: **{market_value:.2f} 円(Mock)** （時価評価込み）")

    # ----------------------
    # 販売所
    # ----------------------
    st.markdown("## 🏦 販売所（手数料 2%）")
    update_price()

    dates, prices = zip(*st.session_state.price_history)
    fig, ax = plt.subplots()
    ax.plot(dates, prices, marker="o")
    ax.set_title("Price History")
    ax.set_ylabel("Price")
    st.pyplot(fig)

    st.write(f"現在価格: **1.00 Ycoin = {st.session_state.market_price:.2f} 円(Mock)**")

    st.write("取引履歴（直近10件）")
    df = pd.DataFrame(st.session_state.trade_history)
    if not df.empty:
        st.dataframe(df.head(10))

    side = st.radio("売買選択", ["buy", "sell"], horizontal=True)
    amount = st.number_input("数量 (Ycoin)", min_value=0.01, step=0.01)
    if st.button("販売所で実行"):
        execute_trade(user, side, amount, "販売所")

    # ----------------------
    # 取引所
    # ----------------------
    st.markdown("## 🔄 取引所（手数料 0.5%）")
    st.write("買い板 / 売り板（ダミー表示中）")

    st.write("取引履歴（直近10件）")
    df = pd.DataFrame(st.session_state.trade_history)
    if not df.empty:
        st.dataframe(df.head(10))

    side = st.radio("売買選択", ["buy", "sell"], horizontal=True, key="ex_side")
    amount = st.number_input("数量 (Ycoin)", min_value=0.01, step=0.01, key="ex_amt")
    if st.button("取引所で実行"):
        execute_trade(user, side, amount, "取引所")

    # ----------------------
    # ダミートレード
    # ----------------------
    simulate_dummy_trades()

    # ----------------------
    # Hostだけ履歴削除
    # ----------------------
    if user == "Host":
        if st.button("取引履歴を全削除"):
            st.session_state.trade_history = []
            st.success("取引履歴を削除しました")

