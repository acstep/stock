"""
streamless-html.py – HTML Viewer
Streamlit app that reads index.html from local directory or GitHub
and displays it in the browser.
"""

import os
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import urllib.request
import urllib.error

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
    
    st.title("📄 HTML Viewer")
    st.caption("從本地檔案或 GitHub 讀取並顯示 index.html")
    
    # Create tabs for different input methods
    tab1, tab2 = st.tabs(["📁 本地檔案", "🌐 GitHub URL"])
    
    html_content = None
    
    with tab1:
        st.subheader("讀取本地 index.html")
        st.info("📂 將會讀取與此腳本同目錄下的 index.html 檔案")
        
        if st.button("讀取本地檔案", type="primary", use_container_width=True):
            with st.spinner("正在讀取檔案..."):
                html_content = read_local_html()
                if html_content:
                    st.success(f"✅ 成功讀取檔案（{len(html_content)} 字元）")
                    st.session_state["html_content"] = html_content
                else:
                    st.error("❌ 找不到 index.html 檔案，請確認檔案存在於同目錄下")
    
    with tab2:
        st.subheader("從 GitHub 讀取 HTML")
        st.info("💡 可以輸入 GitHub 檔案 URL 或 raw.githubusercontent.com URL")
        
        github_url = st.text_input(
            "GitHub URL",
            placeholder="https://github.com/user/repo/blob/main/index.html",
            help="輸入完整的 GitHub 檔案 URL"
        )
        
        if st.button("從 GitHub 讀取", type="primary", use_container_width=True):
            if github_url:
                with st.spinner("正在從 GitHub 讀取..."):
                    html_content = read_github_html(github_url)
                    if html_content:
                        st.success(f"✅ 成功讀取檔案（{len(html_content)} 字元）")
                        st.session_state["html_content"] = html_content
            else:
                st.warning("請先輸入 GitHub URL")
    
    # Display HTML content
    if "html_content" in st.session_state and st.session_state["html_content"]:
        st.divider()
        st.subheader("📋 HTML 預覽")
        
        # Option to show source code
        with st.expander("🔍 查看原始碼", expanded=False):
            st.code(st.session_state["html_content"], language="html")
        
        # Render HTML
        st.markdown("### 渲染結果")
        components.html(
            st.session_state["html_content"],
            height=800,
            scrolling=True
        )


if __name__ == "__main__":
    main()
