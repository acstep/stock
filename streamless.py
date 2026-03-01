"""
streamless.py – Barchart AI Report Generator
Streamlit app that fetches the 4 latest CSVs from Google Drive,
converts them to Markdown, calls Gemini 2.0 Flash, renders the
HTML report, and can save it back to Drive.

st.secrets required:
    GEMINI_API_KEY = "..."

    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
    client_email = "your-sa@your-project.iam.gserviceaccount.com"
    client_id = "..."
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "..."
"""

from __future__ import annotations

import io
import re
from datetime import datetime

import google.generativeai as genai
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/drive"]
TARGET_FOLDER_NAME = "BARCHART"
TOOL_FOLDER_NAME = "tool"
REPORTS_FOLDER_NAME = "reports"
PROMPT_FILENAME = "barchart_prompt.txt"

CSV_TARGETS = [
    ("$SPX", "volume"),
    ("$SPX", "delta"),
    ("$NDX", "volume"),
    ("$NDX", "delta"),
]

# ---------------------------------------------------------------------------
# Google Drive helpers
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_drive_service():
    """Build and return an authenticated Google Drive v3 service."""
    sa_info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def find_folder(service, name: str, parent_id: str | None = None) -> str | None:
    """Return the Drive folder ID matching *name* (optionally inside *parent_id*)."""
    q_parts = [
        "mimeType='application/vnd.google-apps.folder'",
        f"name='{name}'",
        "trashed=false",
    ]
    if parent_id:
        q_parts.append(f"'{parent_id}' in parents")
    result = (
        service.files()
        .list(q=" and ".join(q_parts), fields="files(id, name)", pageSize=1)
        .execute()
    )
    files = result.get("files", [])
    return files[0]["id"] if files else None


def ensure_folder(service, name: str, parent_id: str) -> str:
    """Find *name* folder inside *parent_id*, creating it if missing. Returns folder ID."""
    folder_id = find_folder(service, name, parent_id)
    if folder_id:
        return folder_id
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def list_folder_contents(service, folder_id: str) -> list[dict]:
    """List all files and folders inside folder_id."""
    try:
        result = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=100,
                fields="files(id, name, mimeType)",
            )
            .execute()
        )
        return result.get("files", [])
    except Exception as e:
        st.error(f"🔴 無法列出文件夾內容：{e}")
        return []


def get_latest_csv(
    service, folder_id: str, symbol: str, suffix: str
) -> tuple[str, str] | tuple[None, None]:
    """
    Return (file_id, file_name) for the most-recently modified CSV whose
    name contains *symbol* and ends with *-{suffix}.csv*.
    """
    # Remove $ from symbol for searching (e.g. "$SPX" → search "SPX")
    symbol_search = symbol.replace("$", "")
    
    q = (
        f"'{folder_id}' in parents"
        f" and name contains '{symbol_search}'"
        f" and name contains '-{suffix}.csv'"
        " and mimeType='text/csv'"
        " and trashed=false"
    )
    try:
        result = (
            service.files()
            .list(
                q=q,
                orderBy="modifiedTime desc",
                pageSize=1,
                fields="files(id, name)",
            )
            .execute()
        )
        files = result.get("files", [])
        if not files:
            return None, None
        return files[0]["id"], files[0]["name"]
    except Exception as e:
        st.error(f"🔴 搜尋 {symbol} {suffix} CSV 時出錯：{e}")
        return None, None


def download_file_bytes(service, file_id: str, filename: str = "") -> bytes:
    """Download a Drive file and return its raw bytes."""
    try:
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request, chunksize=256*1024)
        done = False
        while not done:
            try:
                _, done = downloader.next_chunk()
            except Exception as e:
                st.warning(f"⚠️ 下載 {filename} 時超時或出錯：{e}")
                break
        result = buf.getvalue()
        if len(result) == 0:
            st.warning(f"⚠️ {filename} 下載為空，可能是存取權限限制")
        return result
    except Exception as e:
        st.warning(f"⚠️ 無法下載 {filename}：{e}")
        return b""


def download_csv_as_df(service, file_id: str, filename: str = "") -> pd.DataFrame:
    """Download a CSV file from Drive and return a DataFrame."""
    raw = download_file_bytes(service, file_id, filename)
    if not raw or len(raw) == 0:
        return pd.DataFrame()  # Return empty DataFrame if download failed
    try:
        return pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        st.warning(f"⚠️ 解析 {filename} CSV 失敗：{e}")
        return pd.DataFrame()  # Return empty DataFrame if parsing fails


def read_text_file(service, folder_id: str, filename: str) -> str:
    """
    Find *filename* inside *folder_id* and return its decoded text content.
    Handles both plain text files and Google Docs native format.
    Returns empty string if not found or on error.
    """
    try:
        q = (
            f"'{folder_id}' in parents"
            f" and name='{filename}'"
            " and trashed=false"
        )
        result = (
            service.files()
            .list(q=q, pageSize=1, fields="files(id, name, mimeType)")
            .execute()
        )
        files = result.get("files", [])
        if not files:
            return ""
        file_id = files[0]["id"]
        mime_type = files[0].get("mimeType", "")

        # Google Docs native format → use export
        if mime_type == "application/vnd.google-apps.document":
            buf = io.BytesIO()
            request = service.files().export_media(fileId=file_id, mimeType="text/plain")
            downloader = MediaIoBaseDownload(buf, request, chunksize=256*1024)
            done = False
            while not done:
                try:
                    _, done = downloader.next_chunk()
                except Exception as chunk_err:
                    return ""  # timeout or error, return empty
            return buf.getvalue().decode("utf-8", errors="replace")

        # Plain file → use get_media
        raw = download_file_bytes(service, file_id, filename)
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""  # Any error, return empty string gracefully


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

MAX_ROWS = 80  # cap rows per table to limit token usage

def df_to_markdown(title: str, df: pd.DataFrame) -> str:
    """Convert a DataFrame to a Markdown table with a section heading."""
    if len(df) > MAX_ROWS:
        df = df.head(MAX_ROWS)
        truncated = True
    else:
        truncated = False
    try:
        table = df.to_markdown(index=False)
    except Exception:
        # Fallback if tabulate is unavailable
        table = df.to_string(index=False)
    note = f"\n\n> ⚠️ 資料已截斷，僅顯示前 {MAX_ROWS} 列。" if truncated else ""
    return f"### {title}\n\n{table}{note}"


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

def run_gemini_analysis(prompt_text: str, markdown_tables: list[str]) -> str:
    """Call Gemini 2.0 Flash and return the raw response text."""
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel("Gemma 3 27B")

    tables_block = "\n\n".join(markdown_tables)
    full_prompt = (
        f"{prompt_text}\n\n"
        f"以下是最新的四份數據表格（Markdown 格式）：\n\n"
        f"{tables_block}\n\n"
        "請根據上方的分析指引與數據，僅輸出一段完整的 HTML + CSS 代碼，"
        "不要包含任何其他說明文字或 Markdown 標記。"
    )
    response = model.generate_content(full_prompt)
    return response.text


def extract_html(raw: str) -> str:
    """Strip fenced code block markers (```html ... ```) if present."""
    raw = raw.strip()
    # Remove leading ```html or ``` fence
    raw = re.sub(r"^```(?:html)?\s*\n?", "", raw, flags=re.IGNORECASE)
    # Remove trailing ``` fence
    raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip()


# ---------------------------------------------------------------------------
# Drive report saving
# ---------------------------------------------------------------------------

def save_html_to_drive(service, barchart_folder_id: str, html_content: str) -> str:
    """
    Save *html_content* to BARCHART/reports/ with a timestamped filename.
    Returns the filename used.
    """
    reports_folder_id = ensure_folder(service, REPORTS_FOLDER_NAME, barchart_folder_id)
    filename = f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
    metadata = {"name": filename, "parents": [reports_folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(html_content.encode("utf-8")),
        mimetype="text/html",
        resumable=True,
    )
    service.files().create(body=metadata, media_body=media, fields="id").execute()
    return filename


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Barchart AI Report",
        page_icon="📊",
        layout="wide",
    )
    st.title("📊 Barchart AI Report Generator")
    st.caption(
        "從 Google Drive 讀取最新的 $SPX / $NDX gamma & delta 資料，"
        "透過 Gemini 2.0 Flash 生成量化分析 HTML 報告。"
    )

    # Input fields for ES and NQ spreads
    col1, col2 = st.columns(2)
    with col1:
        es_spread = st.number_input(
            "ES = SPX + 多少點？",
            min_value=-100.0,
            max_value=100.0,
            value=0.0,
            step=0.25,
            help="輸入 ES 相對於 SPX 的點差"
        )
    with col2:
        nq_spread = st.number_input(
            "NQ = NDX + 多少點？",
            min_value=-100.0,
            max_value=100.0,
            value=0.0,
            step=0.25,
            help="輸入 NQ 相對於 NDX 的點差"
        )

    # Session state init
    if "html_report" not in st.session_state:
        st.session_state["html_report"] = None
    if "barchart_folder_id" not in st.session_state:
        st.session_state["barchart_folder_id"] = None

    # ── Run analysis button ──────────────────────────────────────────────
    if st.button("🚀 執行分析", type="primary", use_container_width=True):
        st.session_state["html_report"] = None  # clear previous result

        with st.status("正在執行分析流程…", expanded=True) as status:

            # 1. Drive service
            st.write("🔗 連接 Google Drive…")
            try:
                service = get_drive_service()
            except Exception as e:
                status.update(label="無法連接 Google Drive", state="error")
                st.error(f"Drive 認證失敗：{e}")
                st.stop()

            # 2. Locate BARCHART folder
            st.write(f"📁 搜尋 {TARGET_FOLDER_NAME} 資料夾…")
            try:
                barchart_id = find_folder(service, TARGET_FOLDER_NAME)
            except Exception as e:
                status.update(label="Drive API 錯誤", state="error")
                st.error(f"Drive API 錯誤詳情：{e}")
                st.stop()
            if not barchart_id:
                status.update(label=f"找不到 {TARGET_FOLDER_NAME} 資料夾", state="error")
                st.error(f"Google Drive 中找不到 '{TARGET_FOLDER_NAME}' 資料夾。")
                st.info(
                    f"💡 如果資料夾存在，請確保已分享給："
                    f"\n`streamlit-google-drive@stock-488810.iam.gserviceaccount.com`"
                    f"\n並且權限設為「編輯者」。"
                )
                st.stop()
            st.session_state["barchart_folder_id"] = barchart_id

            # 3. Fetch 4 CSVs
            st.write("📥 抓取最新 CSV 檔案（共 4 個）…")
            markdown_tables: list[str] = []
            missing: list[str] = []

            for symbol, suffix in CSV_TARGETS:
                label = f"{symbol} {suffix}"
                file_id, file_name = get_latest_csv(service, barchart_id, symbol, suffix)
                if not file_id:
                    missing.append(label)
                    st.warning(f"⚠️ 找不到 {label} 的 CSV 檔案，將略過。")
                    continue
                st.write(f"  ✅ {label} → `{file_name}`")
                df = download_csv_as_df(service, file_id, file_name)
                if df.empty:
                    st.warning(f"⚠️ {label} CSV 下載或解析失敗，將略過。")
                    missing.append(label)
                    continue
                markdown_tables.append(df_to_markdown(f"{label} ({file_name})", df))

            if not markdown_tables:
                status.update(label="未找到任何 CSV 檔案", state="error")
                st.error("所有 CSV 均無法取得，請確認 Drive 資料夾內容。")
                
                # 診斷：列出 BARCHART 文件夾中的所有文件
                st.info("📂 診斷：BARCHART 文件夾中的所有文件：")
                files = list_folder_contents(service, barchart_id)
                if files:
                    for f in files:
                        mime = f.get("mimeType", "unknown")
                        icon = "📁" if "folder" in mime else "📄"
                        st.write(f"  {icon} {f['name']} ({mime})")
                else:
                    st.warning("  ⚠️ 文件夾是空的，或者服務帳戶沒有存取權限")
                
                st.stop()

            # 4. Read prompt file
            st.write(f"📄 讀取 {PROMPT_FILENAME}…")
            tool_folder_id = find_folder(service, TOOL_FOLDER_NAME, barchart_id)
            prompt_text = ""
            if tool_folder_id:
                prompt_text = read_text_file(service, tool_folder_id, PROMPT_FILENAME)
            if not prompt_text:
                st.warning(
                    f"⚠️ 找不到 {TARGET_FOLDER_NAME}/{TOOL_FOLDER_NAME}/{PROMPT_FILENAME}，"
                    "將使用預設提示詞繼續分析。"
                )
                prompt_text = (
                    "你是一位專業的量化分析師，請根據以下 $SPX 與 $NDX 的 "
                    "Gamma Exposure volume 及 delta 數據進行深入分析，"
                    "找出關鍵支撐與壓力位，評估市場情緒，並提供交易建議。"
                )
            else:
                st.write(f"  ✅ 已讀取提示詞（{len(prompt_text)} 字元）")

            # Add ES/NQ spread info to the beginning of prompt
            spread_info = (
                f"目前 ES = SPX + {es_spread} 點。NQ = NDX + {nq_spread} 點。"
                f"數據內是 SPX 以及 NDX 的資料。你的分析結果請用 ES 跟 NQ 點數來告訴我。\n\n"
            )
            prompt_text = spread_info + prompt_text

            # Display full prompt
            st.write("📝 完整提示詞：")
            with st.expander("點擊查看完整提示詞內容", expanded=False):
                st.text(prompt_text)

            # 5. Gemini analysis
            st.write("🤖 呼叫 Gemini 2.0 Flash 生成 HTML 報告…")
            try:
                raw_response = run_gemini_analysis(prompt_text, markdown_tables)
                html_report = extract_html(raw_response)
                st.session_state["html_report"] = html_report
            except Exception as e:
                status.update(label="Gemini 分析失敗", state="error")
                st.error(f"Gemini 呼叫發生錯誤：{e}")
                st.stop()

            status.update(label="✅ 分析完成！", state="complete", expanded=False)

    # ── Render HTML report ───────────────────────────────────────────────
    html_report: str | None = st.session_state.get("html_report")
    if html_report:
        st.divider()
        st.subheader("📋 AI 分析報告")

        # Save to Drive button
        if st.button("💾 儲存報告至 Google Drive", use_container_width=True):
            service = get_drive_service()
            barchart_id = st.session_state.get("barchart_folder_id")
            if not barchart_id:
                barchart_id = find_folder(service, TARGET_FOLDER_NAME)
            if barchart_id:
                try:
                    filename = save_html_to_drive(service, barchart_id, html_report)
                    st.success(
                        f"✅ 報告已成功儲存至 Google Drive！\n\n"
                        f"路徑：`{TARGET_FOLDER_NAME}/{REPORTS_FOLDER_NAME}/{filename}`"
                    )
                except Exception as e:
                    st.error(f"儲存失敗：{e}")
            else:
                st.error(f"找不到 Google Drive 中的 '{TARGET_FOLDER_NAME}' 資料夾。")

        # Render HTML
        components.html(html_report, height=900, scrolling=True)


if __name__ == "__main__":
    main()
