import streamlit as st
import os
import json
from datetime import datetime
import pytz

from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

from langchain_google_community import CalendarToolkit
from langchain_google_community.calendar.utils import build_calendar_service
from google.oauth2 import service_account

# -------------------- PAGE CONFIG --------------------
st.set_page_config(page_title="Calendar AI Agent", page_icon="📅", layout="wide")
st.title("📅 Google Calendar AI Agent")

# -------------------- LOAD SECRETS --------------------
os.environ['OPENAI_API_KEY'] = st.secrets["OPENAI_API_KEY"]
os.environ['GROQ_API_KEY'] = st.secrets["GROQ_API_KEY"]

# -------------------- SESSION INIT --------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = "chat-session"

# -------------------- CACHE: TOOLKIT --------------------
@st.cache_resource
def get_calendar_tools():
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])

    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/calendar']
    )

    service = build_calendar_service(credentials=credentials)

    # 🔥 Monkey patch (fix OAuth issue)
    import langchain_google_community.calendar.utils as cal_utils
    cal_utils.get_google_credentials = lambda *args, **kwargs: credentials

    toolkit = CalendarToolkit(service=service).get_tools()

    return toolkit

# -------------------- CACHE: AGENT --------------------
@st.cache_resource
def get_agent(toolkit):
    model = ChatOpenAI(
        model='gpt-4.1-mini-2025-04-14',
        temperature=0.3,
        max_completion_tokens=512
    )

    summarize_model = ChatGroq(
        model='llama-3.1-8b-instant',
        temperature=0.4
    )

    tz = pytz.timezone("Asia/Karachi")
    current_time = datetime.now(tz).isoformat()

    system_prompt = f"""
    You are a smart calendar assistant.

    Current time: {current_time}

    You can:
    - Check events
    - Create events
    - Update events

    Always use tools when needed.
    """

    agent = create_agent(
        model=model,
        tools=toolkit,
        checkpointer=InMemorySaver(),
        middleware=[
            SummarizationMiddleware(
                model=summarize_model,
                trigger=("tokens", 4000),
                keep=("messages", 25)
            )
        ],
        system_prompt=system_prompt
    )

    return agent

# -------------------- INIT --------------------
toolkit = get_calendar_tools()
agent = get_agent(toolkit)

# -------------------- DISPLAY CHAT --------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -------------------- USER INPUT --------------------
user_input = st.chat_input("Ask about your calendar...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response_text = ""

            # ✅ STREAM FIX (prevents tool_call errors)
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": user_input}]},
                config={"configurable": {"thread_id": st.session_state.thread_id}}
            ):
                if "messages" in chunk:
                    response_text = chunk["messages"][-1].content

            st.markdown(response_text)

    st.session_state.messages.append({"role": "assistant", "content": response_text})

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.header("⚙️ Settings")

    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ Notes")
    st.markdown("""
- Calendar must be shared with service account  
- Secrets must be configured correctly  
- Supports create, read, update events  
""")
