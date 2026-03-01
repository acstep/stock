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


def get_html_files_list() -> list[Path]:
    """Get list of all HTML files in data subdirectory."""
    try:
        current_dir = Path(__file__).parent
        data_dir = current_dir / "data"
        
        if not data_dir.exists():
            return []
        
        # Find all HTML files and sort by modification time (newest first)
        html_files = list(data_dir.glob("*.html"))
        html_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        return html_files
    except Exception as e:
        st.error(f"獲取 HTML 檔案列表時發生錯誤：{e}")
        return []


def read_html_file(file_path: Path) -> str | None:
    """Read HTML content from a file path."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        st.error(f"讀取檔案時發生錯誤：{e}")
        return None


def estimate_html_height(html_content: str) -> int:
    """Estimate HTML height based on content length."""
    # 計算行數來估算高度
    lines = html_content.count('\n')
    # 基本高度 + 行數 * 每行平均高度 (增加係數)
    line_based = 800 + (lines * 5)
    
    # 同時考慮內容長度 (增加係數)
    content_length = len(html_content)
    content_based = (content_length // 200) * 20
    
    # 檢查是否有表格或複雜結構
    table_count = html_content.count('<table') + html_content.count('<tr')
    table_bonus = table_count * 30
    
    # 取最大值，設定最小值2000px，最大值100000px
    estimated_height = max(line_based, content_based, 2000) + table_bonus
    return min(estimated_height, 100000)


# ---------------------------------------------------------------------------
# Yahoo Finance helpers
# ---------------------------------------------------------------------------

def get_futures_data(symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame | None:
    """Fetch futures data from Yahoo Finance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
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


def create_candlestick_chart(df: pd.DataFrame, title: str, show_bollinger: bool = True) -> go.Figure:
    """Create a candlestick chart with optional Bollinger Bands."""
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
    
    # Bollinger Bands (only if show_bollinger is True and columns exist)
    if show_bollinger and 'Upper' in df.columns:
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
    
    # Get list of HTML files
    html_files = get_html_files_list()
    
    html_content = None
    
    if html_files:
        # Create selectbox for HTML file selection
        st.subheader("📁 選擇 HTML 報告")
        file_options = [f.name for f in html_files]
        selected_file = st.selectbox(
            "選擇要顯示的報告",
            options=file_options,
            index=0,
            help="按修改時間排序，最新的在最前面"
        )
        
        # Read selected file
        selected_path = next(f for f in html_files if f.name == selected_file)
        html_content = read_html_file(selected_path)
        
        if html_content:
            st.divider()
            # 自動計算 HTML 高度
            html_height = estimate_html_height(html_content)
            components.html(html_content, height=html_height, scrolling=False)
        else:
            st.error("❌ 無法讀取 HTML 檔案")
    else:
        st.error("❌ data 目錄中找不到 HTML 檔案")
    
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
    
    # Display 1-minute charts
    st.divider()
    st.subheader("📊 ES & NQ 一分鐘線圖")
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown("### ES 一分鐘線圖")
        with st.spinner("正在獲取 ES 一分鐘數據..."):
            # Try to get data for last 5 days to ensure we get the latest trading day
            es_1m_data = get_futures_data("ES=F", period="5d", interval="1m")
            if es_1m_data is not None and not es_1m_data.empty:
                # Get the latest trading day
                latest_date = es_1m_data.index[-1].date()
                es_1m_today = es_1m_data[es_1m_data.index.date == latest_date]
                
                if not es_1m_today.empty:
                    st.caption(f"數據日期：{latest_date}")
                    fig_es_1m = create_candlestick_chart(es_1m_today, "ES 一分鐘K線圖", show_bollinger=False)
                    st.plotly_chart(fig_es_1m, use_container_width=True)
    
    with col4:
        st.markdown("### NQ 一分鐘線圖")
        with st.spinner("正在獲取 NQ 一分鐘數據..."):
            # Try to get data for last 5 days to ensure we get the latest trading day
            nq_1m_data = get_futures_data("NQ=F", period="5d", interval="1m")
            if nq_1m_data is not None and not nq_1m_data.empty:
                # Get the latest trading day
                latest_date = nq_1m_data.index[-1].date()
                nq_1m_today = nq_1m_data[nq_1m_data.index.date == latest_date]
                
                if not nq_1m_today.empty:
                    st.caption(f"數據日期：{latest_date}")
                    fig_nq_1m = create_candlestick_chart(nq_1m_today, "NQ 一分鐘K線圖", show_bollinger=False)
                    st.plotly_chart(fig_nq_1m, use_container_width=True)


if __name__ == "__main__":
    main()
