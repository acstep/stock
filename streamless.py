"""
streamless-html.py – HTML Viewer
Streamlit app that reads index.html from local directory or GitHub
and displays it in the browser, with ES/NQ candlestick charts.
"""

import os
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import urllib.request
import urllib.error
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# HTML loading helpers
# ---------------------------------------------------------------------------

def read_local_html(filename: str = "index.html") -> str | None:
    """Read HTML file from the same directory as this script."""
    try:
        current_dir = Path(__file__).parent
        html_path = current_dir / filename
        
        if html_path.exists():
            with open(html_path, "r", encoding="utf-8") as f:
                return f.read()
        return None
    except Exception as e:
        st.error(f"讀取本地檔案時發生錯誤：{e}")
        return None


def get_latest_html_in_data() -> str | None:
    """Get the latest HTML file from the data subdirectory."""
    try:
        current_dir = Path(__file__).parent
        data_dir = current_dir / "data"
        
        if not data_dir.exists():
            st.error(f"❌ data 目錄不存在")
            return None
        
        # Find all HTML files
        html_files = list(data_dir.glob("*.html"))
        
        if not html_files:
            st.error("❌ data 目錄中找不到 HTML 檔案")
            return None
        
        # Get the latest modified file
        latest_file = max(html_files, key=lambda p: p.stat().st_mtime)
        
        with open(latest_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        st.error(f"讀取 data 目錄中的 HTML 檔案時發生錯誤：{e}")
        return None


# ---------------------------------------------------------------------------
# Yahoo Finance helpers
# ---------------------------------------------------------------------------

def get_futures_data(symbol: str, period: str = "3mo") -> pd.DataFrame | None:
    """Fetch futures data from Yahoo Finance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        if df.empty:
            st.warning(f"⚠️ 無法獲取 {symbol} 數據")
            return None
        return df
    except Exception as e:
        st.error(f"獲取 {symbol} 數據時發生錯誤：{e}")
        return None


def calculate_bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Calculate Bollinger Bands."""
    df = df.copy()
    df['SMA'] = df['Close'].rolling(window=window).mean()
    df['STD'] = df['Close'].rolling(window=window).std()
    df['Upper'] = df['SMA'] + (df['STD'] * num_std)
    df['Lower'] = df['SMA'] - (df['STD'] * num_std)
    return df


def create_candlestick_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """Create a candlestick chart with Bollinger Bands."""
    fig = go.Figure()
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='K線',
        increasing_line_color='red',
        decreasing_line_color='green'
    ))
    
    # Bollinger Bands
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Upper'],
        name='上軌',
        line=dict(color='rgba(250, 128, 114, 0.5)', width=1),
        mode='lines'
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['SMA'],
        name='中軌 (SMA20)',
        line=dict(color='orange', width=1.5),
        mode='lines'
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Lower'],
        name='下軌',
        line=dict(color='rgba(173, 216, 230, 0.5)', width=1),
        mode='lines',
        fill='tonexty',
        fillcolor='rgba(173, 216, 230, 0.1)'
    ))
    
    fig.update_layout(
        title=title,
        yaxis_title='價格',
        xaxis_title='日期',
        height=500,
        template='plotly_white',
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig


def read_github_html(url: str) -> str | None:
    """Read HTML content from a GitHub raw URL."""
    try:
        # Convert GitHub URL to raw URL if needed
        if "github.com" in url and "raw.githubusercontent.com" not in url:
            # Convert https://github.com/user/repo/blob/branch/path
            # to https://raw.githubusercontent.com/user/repo/branch/path
            url = url.replace("github.com", "raw.githubusercontent.com")
            url = url.replace("/blob/", "/")
        
        with urllib.request.urlopen(url, timeout=10) as response:
            content = response.read().decode("utf-8")
            return content
    except urllib.error.URLError as e:
        st.error(f"無法從 GitHub 讀取檔案：{e}")
        return None
    except Exception as e:
        st.error(f"讀取 GitHub 檔案時發生錯誤：{e}")
        return None


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="HTML Viewer",
        page_icon="📄",
        layout="wide",
    )
    
    # Directly read and display latest HTML from data subdirectory
    html_content = get_latest_html_in_data()
    
    if html_content:
        components.html(html_content, height=800, scrolling=True)
    else:
        st.error("❌ 無法讀取 HTML 檔案")
    
    # Display ES and NQ charts with Bollinger Bands
    st.divider()
    st.subheader("📈 ES & NQ 日K線圖 (含布林帶指標)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### ES (E-mini S&P 500)")
        with st.spinner("正在獲取 ES 數據..."):
            es_data = get_futures_data("ES=F", period="3mo")
            if es_data is not None:
                es_data = calculate_bollinger_bands(es_data)
                
                # Display latest Bollinger Bands values
                latest = es_data.iloc[-1]
                st.info(f"**最後一天 ({latest.name.strftime('%Y-%m-%d')})**\n\n"
                       f"📈 布林上軌：**{latest['Upper']:.2f}**\n\n"
                       f"📉 布林下軌：**{latest['Lower']:.2f}**")
                
                fig_es = create_candlestick_chart(es_data, "ES 日K線圖 + 布林通道")
                st.plotly_chart(fig_es, use_container_width=True)
    
    with col2:
        st.markdown("### NQ (E-mini Nasdaq-100)")
        with st.spinner("正在獲取 NQ 數據..."):
            nq_data = get_futures_data("NQ=F", period="3mo")
            if nq_data is not None:
                nq_data = calculate_bollinger_bands(nq_data)
                
                # Display latest Bollinger Bands values
                latest = nq_data.iloc[-1]
                st.info(f"**最後一天 ({latest.name.strftime('%Y-%m-%d')})**\n\n"
                       f"📈 布林上軌：**{latest['Upper']:.2f}**\n\n"
                       f"📉 布林下軌：**{latest['Lower']:.2f}**")
                
                fig_nq = create_candlestick_chart(nq_data, "NQ 日K線圖 + 布林通道")
                st.plotly_chart(fig_nq, use_container_width=True)


if __name__ == "__main__":
    main()
