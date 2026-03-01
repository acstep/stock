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


if __name__ == "__main__":
    main()
