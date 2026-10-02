import streamlit as st

import os
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

st.title("My very first Chatbot")

for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if usr_input := st.chat_input("Enter your msg"):
    with st.chat_message("user"):
        st.write(usr_input)
    st.session_state["chat_history"].append({"role": "user", "content": usr_input})
    
    response = client.chat.completions.create(
        model="openai/gpt-5.4",
        #messages=[{"role": "user", "content": usr_input}],
        messages=st.session_state["chat_history"]
    )

    bot_feedback = response.choices[0].message.content

    with st.chat_message("assistant"):
        st.write(bot_feedback + f"  \n(Total token usage: {response.usage.total_tokens})")
        
    st.session_state["chat_history"].append({"role": "assistant", "content": bot_feedback})