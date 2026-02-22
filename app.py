"""
HR-Tech 株価・ニュース 比較ダッシュボード
対象: プラスアルファ・コンサルティング / カオナビ / SmartHR / HRブレイン

依存: pip install -r requirements.txt
起動: streamlit run app.py --browser.gatherUsageStats false
"""

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime
import urllib.parse
import re

# ======================================================================
# 対象企業定義
# ======================================================================
COMPANIES = [
    {
        "name":    "プラスアルファ・コンサルティング",
        "short":   "プラスアルファ",
        "ticker":  "4071.T",
        "code":    "4071",
        "market":  "東証プライム",
        "color":   "#e74c3c",
        "product": "タレントパレット",
        "service": "タレントマネジメント・HR データ分析",
        "target":  "中堅〜大企業",
        "news_q":  "プラスアルファ コンサルティング 4071",
        "ir_url":  "https://www.pa-consul.co.jp/ir/news/",
        "web_url": "https://www.pa-consul.co.jp/",
    },
    {
        "name":    "カオナビ",
        "short":   "カオナビ",
        "ticker":  None,           # 上場廃止
        "code":    "4435（上場廃止）",
        "market":  "上場廃止",
        "color":   "#3498db",
        "product": "カオナビ",
        "service": "クラウド人材管理・組織図・人事データ活用",
        "target":  "中堅〜大企業",
        "news_q":  "カオナビ 人事 HR",
        "ir_url":  "https://corp.kaonavi.jp/news/",
        "web_url": "https://kaonavi.jp/",
    },
    {
        "name":    "SmartHR",
        "short":   "SmartHR",
        "ticker":  None,           # 非上場
        "code":    "非上場",
        "market":  "非上場",
        "color":   "#27ae60",
        "product": "SmartHR",
        "service": "クラウド人事・労務管理・タレントマネジメント",
        "target":  "スタートアップ〜大企業",
        "news_q":  "SmartHR スマートHR",
        "ir_url":  "https://smarthr.co.jp/news/",
        "web_url": "https://smarthr.co.jp/",
    },
    {
        "name":    "HRブレイン",
        "short":   "HRブレイン",
        "ticker":  None,           # 非上場
        "code":    "非上場",
        "market":  "非上場",
        "color":   "#f39c12",
        "product": "HRBrain",
        "service": "タレントマネジメント・人事評価・エンゲージメント",
        "target":  "中堅〜大企業",
        "news_q":  "HRブレイン HRBrain 人事",
        "ir_url":  "https://hrbrain.jp/news/",
        "web_url": "https://hrbrain.jp/",
    },
]

# ======================================================================
# ページ設定
# ======================================================================
st.set_page_config(
    page_title="HR-Tech 比較ダッシュボード",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; padding: 6px 18px; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700; }
    footer { visibility: hidden; }
    .company-badge {
        display: inline-block; padding: 2px 10px; border-radius: 12px;
        font-size: 0.8rem; font-weight: 600; margin-left: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ======================================================================
# チャート共通フォント設定
# ======================================================================
_FONT        = dict(family="Meiryo, Yu Gothic, sans-serif", size=14, color="#2c3e50")
_TITLE_FONT  = dict(family="Meiryo, Yu Gothic, sans-serif", size=17, color="#1a1a2e")
_AXIS_FONT   = dict(size=13, color="#2c3e50")
_TICK_FONT   = dict(size=12, color="#2c3e50")
_LEGEND_FONT = dict(size=13, color="#2c3e50")


def _common_layout(**kwargs) -> dict:
    base = dict(
        font=_FONT,
        title_font=_TITLE_FONT,
        legend=dict(
            font=_LEGEND_FONT,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hoverlabel=dict(font_size=13, bgcolor="white"),
    )
    base.update(kwargs)
    return base


def _style_axes(fig: go.Figure):
    fig.update_xaxes(
        title_font=_AXIS_FONT, tickfont=_TICK_FONT,
        showgrid=True, gridcolor="#ececec", gridwidth=1,
        linecolor="#ccc", linewidth=1, showline=True,
    )
    fig.update_yaxes(
        title_font=_AXIS_FONT, tickfont=_TICK_FONT,
        showgrid=True, gridcolor="#ececec", gridwidth=1,
        linecolor="#ccc", linewidth=1, showline=True,
    )
    return fig


def _ja_date_format(period_label: str) -> str:
    """表示期間に応じた日本語日付フォーマット（D3 tickformat）を返す"""
    if period_label in ("1週間", "1ヶ月"):
        return "%m月%d日"
    return "%Y年%m月"


# ======================================================================
# データ取得（キャッシュ付き）
# ======================================================================

@st.cache_data(ttl=300)
def fetch_stock(ticker: str, period: str):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        info = {}
        try:
            info = t.info
        except Exception:
            pass
        return hist, info
    except Exception:
        return pd.DataFrame(), {}


@st.cache_data(ttl=600)
def fetch_google_news(query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        feed = feedparser.parse(url)
        results = []
        for e in feed.entries[:20]:
            pub = ""
            if getattr(e, "published_parsed", None):
                pub = datetime(*e.published_parsed[:6]).strftime("%Y-%m-%d")
            src = getattr(getattr(e, "source", None), "title", "Google News")
            results.append({
                "date":   pub,
                "title":  e.get("title", ""),
                "link":   e.get("link", ""),
                "source": src,
            })
        return results
    except Exception:
        return []


@st.cache_data(ttl=600)
def fetch_ir_news(url: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    }
    results = []
    DATE_PAT = re.compile(r"\d{4}[./年]\d{1,2}[./月]\d{1,2}")

    def _extract_date(node) -> str:
        for s in node.stripped_strings:
            if DATE_PAT.search(s):
                return s.strip()
        return ""

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        # パターン1: ul > li > a
        for ul in soup.find_all("ul"):
            items = ul.find_all("li")
            batch = []
            for li in items:
                a = li.find("a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                if len(title) < 5:
                    continue
                href = a.get("href", "")
                if href and not href.startswith("http"):
                    href = urllib.parse.urljoin(url, href)
                batch.append({"date": _extract_date(li), "title": title,
                              "link": href, "source": "IR"})
            if len(batch) >= 3:
                results = batch[:20]
                break

        # パターン2: dl > dt + dd
        if not results:
            for dl in soup.find_all("dl"):
                dts = dl.find_all("dt")
                dds = dl.find_all("dd")
                if len(dts) < 2:
                    continue
                batch = []
                for dt, dd in zip(dts, dds):
                    a = dd.find("a") or dt.find("a")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if href and not href.startswith("http"):
                        href = urllib.parse.urljoin(url, href)
                    batch.append({"date": _extract_date(dt) or _extract_date(dd),
                                  "title": title, "link": href, "source": "IR"})
                if len(batch) >= 2:
                    results = batch[:20]
                    break
    except Exception:
        pass
    return results


# ======================================================================
# チャート作成
# ======================================================================

def make_stock_chart(hist: pd.DataFrame, comp: dict, period_label: str) -> go.Figure:
    """ローソク足 + 移動平均 + 出来高"""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.04, row_heights=[0.75, 0.25],
    )
    fig.add_trace(go.Candlestick(
        x=hist.index,
        open=hist["Open"], high=hist["High"],
        low=hist["Low"],  close=hist["Close"],
        name="株価",
        increasing=dict(line=dict(color="#e74c3c"), fillcolor="#e74c3c"),
        decreasing=dict(line=dict(color="#3498db"), fillcolor="#3498db"),
    ), row=1, col=1)

    df_ma = hist.copy()
    for window, color, dash in [(5, "orange", "solid"), (25, "#8e44ad", "solid"), (75, "#27ae60", "dot")]:
        if len(df_ma) >= window:
            df_ma[f"MA{window}"] = df_ma["Close"].rolling(window).mean()
            fig.add_trace(go.Scatter(
                x=df_ma.index, y=df_ma[f"MA{window}"],
                name=f"{window}日MA",
                line=dict(color=color, width=1.5, dash=dash),
                opacity=0.85,
            ), row=1, col=1)

    vol_colors = ["#e74c3c" if c >= o else "#3498db"
                  for c, o in zip(hist["Close"], hist["Open"])]
    fig.add_trace(go.Bar(
        x=hist.index, y=hist["Volume"], name="出来高",
        marker_color=vol_colors, opacity=0.65,
    ), row=2, col=1)

    fig.update_layout(**_common_layout(
        title=f"{comp['name']}（{comp['code']}）ローソク足チャート（{period_label}）",
        xaxis_rangeslider_visible=False,
        height=620,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=_LEGEND_FONT,
                    bgcolor="rgba(255,255,255,0.9)", bordercolor="#ddd", borderwidth=1),
        yaxis_title="株価（円）",
        yaxis2_title="出来高",
        margin=dict(l=70, r=30, t=90, b=30),
        hovermode="x unified",
    ))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1)
    _style_axes(fig)
    fig.update_xaxes(tickformat=_ja_date_format(period_label))
    return fig


def make_line_chart(hist: pd.DataFrame, comp: dict, period_label: str) -> go.Figure:
    """終値推移（折れ線）"""
    close = hist["Close"]
    color = "#e74c3c" if close.iloc[-1] >= close.iloc[0] else "#3498db"
    rgb = ",".join(str(int(color[i:i+2], 16)) for i in (1, 3, 5))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index, y=close,
        mode="lines", name="終値",
        line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=f"rgba({rgb},0.08)",
        hovertemplate="%{x|%Y-%m-%d}<br>終値: %{y:,.0f}円<extra></extra>",
    ))
    fig.add_hline(
        y=close.iloc[0], line_dash="dot", line_color="gray", opacity=0.6,
        annotation_text=f"起点 {close.iloc[0]:,.0f}円",
        annotation_position="right",
    )
    fig.update_layout(**_common_layout(
        title=f"{comp['short']} 終値推移（{period_label}）",
        height=480, xaxis_title="日付", yaxis_title="株価（円）",
        margin=dict(l=70, r=30, t=70, b=50),
        hovermode="x unified",
    ))
    _style_axes(fig)
    fig.update_xaxes(tickformat=_ja_date_format(period_label))
    return fig


def make_volume_chart(hist: pd.DataFrame, comp: dict, period_label: str) -> go.Figure:
    """出来高棒グラフ"""
    vol_colors = ["#e74c3c" if c >= o else "#3498db"
                  for c, o in zip(hist["Close"], hist["Open"])]
    fig = go.Figure(go.Bar(
        x=hist.index, y=hist["Volume"],
        marker_color=vol_colors, opacity=0.75, name="出来高",
        hovertemplate="%{x|%Y-%m-%d}<br>出来高: %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(**_common_layout(
        title=f"{comp['short']} 出来高（{period_label}）",
        height=400, xaxis_title="日付", yaxis_title="出来高",
        margin=dict(l=70, r=30, t=70, b=50),
    ))
    _style_axes(fig)
    fig.update_xaxes(tickformat=_ja_date_format(period_label))
    return fig


# ======================================================================
# 企業概要・株価指標 比較表
# ======================================================================

def build_overview_table() -> pd.DataFrame:
    rows = []
    for c in COMPANIES:
        rows.append({
            "会社名":       c["name"],
            "上場状況":     c["market"],
            "証券コード":   c["code"],
            "主力製品":     c["product"],
            "サービス概要": c["service"],
            "ターゲット":   c["target"],
            "公式サイト":   c["web_url"],
        })
    return pd.DataFrame(rows).set_index("会社名")


def build_stock_metrics_table(stocks: dict, period_label: str) -> pd.DataFrame:
    rows = []
    for comp in COMPANIES:
        name = comp["name"]
        if name not in stocks or stocks[name][0].empty:
            rows.append({
                "会社名":    comp["short"],
                "現在値（円）": "---",
                "前日比（%）": "---",
                f"期間騰落率（{period_label}）": "---",
                "期間高値（円）": "---",
                "期間安値（円）": "---",
                "PER（倍）": "---",
                "PBR（倍）": "---",
                "備考":      comp["market"],
            })
            continue
        hist, info = stocks[name]
        latest  = hist.iloc[-1]
        prev    = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
        price   = latest["Close"]
        chg_pct = (price - prev["Close"]) / prev["Close"] * 100 if prev["Close"] else 0
        ret     = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
        per = info.get("trailingPE")
        pbr = info.get("priceToBook")
        rows.append({
            "会社名":    comp["short"],
            "現在値（円）": f"{price:,.0f}",
            "前日比（%）": f"{chg_pct:+.2f}%",
            f"期間騰落率（{period_label}）": f"{ret:+.2f}%",
            "期間高値（円）": f"{hist['High'].max():,.0f}",
            "期間安値（円）": f"{hist['Low'].min():,.0f}",
            "PER（倍）": f"{per:.1f}" if per else "---",
            "PBR（倍）": f"{pbr:.2f}" if pbr else "---",
            "備考":      comp["market"],
        })
    return pd.DataFrame(rows).set_index("会社名")


# ======================================================================
# 表示ヘルパー
# ======================================================================

def render_stock_metrics(hist: pd.DataFrame, info: dict, period_label: str):
    latest  = hist.iloc[-1]
    prev    = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
    price   = latest["Close"]
    chg     = price - prev["Close"]
    chg_pct = chg / prev["Close"] * 100 if prev["Close"] else 0
    ret     = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
    per = info.get("trailingPE")
    pbr = info.get("priceToBook")

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("現在値（円）", f"{price:,.0f}", f"{chg:+.0f}（{chg_pct:+.2f}%）")
    c2.metric("出来高",      f"{int(latest['Volume']):,}")
    c3.metric(f"期間騰落率（{period_label}）", f"{ret:+.2f}%")
    c4.metric("期間高値（円）", f"{hist['High'].max():,.0f}")
    c5.metric("期間安値（円）", f"{hist['Low'].min():,.0f}")
    c6.metric("PER", f"{per:.1f}倍" if per else "---")
    c7.metric("PBR", f"{pbr:.2f}倍" if pbr else "---")


def render_stock_tabs(hist: pd.DataFrame, comp: dict, period_label: str):
    ct1, ct2, ct3, ct4 = st.tabs(["ローソク足", "終値推移", "出来高", "データ表"])
    with ct1:
        st.plotly_chart(make_stock_chart(hist, comp, period_label), use_container_width=True)
    with ct2:
        st.plotly_chart(make_line_chart(hist, comp, period_label), use_container_width=True)
    with ct3:
        st.plotly_chart(make_volume_chart(hist, comp, period_label), use_container_width=True)
    with ct4:
        df_t = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        df_t.index = pd.to_datetime(df_t.index).strftime("%Y-%m-%d")
        df_t.index.name = "日付"
        df_t.columns = ["始値", "高値", "安値", "終値", "出来高"]
        df_t["前日比（円）"] = df_t["終値"].diff().round(0)
        df_t["前日比（%）"] = (df_t["終値"].pct_change() * 100).round(2)
        df_t = df_t.iloc[::-1]

        def _color(val):
            try:
                v = float(val)
                return "color: #e74c3c" if v > 0 else ("color: #3498db" if v < 0 else "")
            except (TypeError, ValueError):
                return ""

        styled = (
            df_t.style
            .format({
                "始値": "{:,.0f}", "高値": "{:,.0f}",
                "安値": "{:,.0f}", "終値": "{:,.0f}", "出来高": "{:,.0f}",
                "前日比（円）": lambda x: f"{x:+.0f}" if pd.notna(x) else "---",
                "前日比（%）": lambda x: f"{x:+.2f}%" if pd.notna(x) else "---",
            })
            .map(_color, subset=["前日比（円）", "前日比（%）"])
        )
        st.dataframe(styled, use_container_width=True, height=500)


def render_news(comp: dict):
    col_gn, col_ir = st.columns(2)

    with col_gn:
        st.markdown("**Google News**")
        with st.spinner("取得中..."):
            items = fetch_google_news(comp["news_q"])
        if not items:
            st.info("ニュースが見つかりませんでした。")
        else:
            for item in items[:10]:
                if item["link"]:
                    st.markdown(f"[{item['title']}]({item['link']})")
                else:
                    st.markdown(item["title"])
                st.caption(f"{item['date']} | {item['source']}")
                st.divider()

    with col_ir:
        st.markdown("**IR / ニュース**")
        with st.spinner("取得中..."):
            items = fetch_ir_news(comp["ir_url"])
        if not items:
            st.info("自動取得できませんでした。")
            st.markdown(f"[公式ページを開く]({comp['ir_url']})")
        else:
            for item in items[:10]:
                if item["link"]:
                    st.markdown(f"[{item['title']}]({item['link']})")
                else:
                    st.markdown(item["title"])
                if item["date"]:
                    st.caption(item["date"])
                st.divider()


# ======================================================================
# メイン
# ======================================================================

def main():
    # ── サイドバー ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## HR-Tech 比較ダッシュボード")
        st.divider()

        period_map = {
            "1週間": "5d", "1ヶ月": "1mo", "3ヶ月": "3mo",
            "6ヶ月": "6mo", "1年": "1y", "3年": "3y", "5年": "5y",
        }
        period_label = st.selectbox("表示期間", list(period_map.keys()), index=2)
        period = period_map[period_label]

        st.divider()
        auto_refresh = st.toggle("自動更新", value=True)
        refresh_min = 5
        if auto_refresh:
            refresh_min = st.select_slider(
                "更新間隔（分）", options=[1, 2, 5, 10, 15, 30], value=5
            )

        st.divider()
        st.markdown("**対象企業**")
        for comp in COMPANIES:
            icon = "📈" if comp["ticker"] else ("🔒" if comp["market"] == "上場廃止" else "🏢")
            st.markdown(f"{icon} **{comp['short']}** — {comp['market']}")

        st.divider()
        st.markdown("**公式リンク**")
        for comp in COMPANIES:
            st.markdown(f"[{comp['short']}]({comp['web_url']})")

    # ── 自動更新（JS）───────────────────────────────────────────────────
    if auto_refresh:
        components.html(f"""
            <script>
                setTimeout(function() {{ window.parent.location.reload(); }},
                           {refresh_min * 60 * 1000});
            </script>
        """, height=0)

    # ── ヘッダー ────────────────────────────────────────────────────────
    col_title, col_btn = st.columns([6, 1])
    with col_title:
        st.title("📊 HR-Tech 株価・ニュース 比較ダッシュボード")
        st.caption(
            "対象: " + " ／ ".join(c["short"] for c in COMPANIES)
            + f"　|　最終更新: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"
            + (f"　|　{refresh_min}分毎に自動更新中" if auto_refresh else "")
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 手動更新", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # ── 株価データ取得（上場企業のみ）────────────────────────────────────
    stocks: dict = {}
    with st.spinner("株価データを取得中..."):
        for comp in COMPANIES:
            if comp["ticker"]:
                hist, info = fetch_stock(comp["ticker"], period)
                stocks[comp["name"]] = (hist, info)

    # ── タブ ────────────────────────────────────────────────────────────
    tab_labels = ["📊 4社比較"] + [
        ("📈 " if c["ticker"] else "📰 ") + c["short"]
        for c in COMPANIES
    ]
    tab_compare, *company_tabs = st.tabs(tab_labels)

    # ════════════════════════════════════════════
    # 比較タブ
    # ════════════════════════════════════════════
    with tab_compare:

        # ① 企業概要比較表
        st.markdown("### 企業概要比較")
        st.dataframe(build_overview_table(), use_container_width=True)

        st.divider()

        # ② 株価指標比較表
        st.markdown("### 株価指標比較")
        st.dataframe(build_stock_metrics_table(stocks, period_label), use_container_width=True)
        st.caption(
            "※ カオナビは上場廃止のためデータなし。"
            "SmartHR・HRブレインは非上場のためデータなし。"
        )

    # ════════════════════════════════════════════
    # 個別企業タブ
    # ════════════════════════════════════════════
    for comp, tab in zip(COMPANIES, company_tabs):
        with tab:
            name = comp["name"]

            status_color = (
                "#27ae60" if comp["ticker"] else
                ("#e67e22" if comp["market"] == "上場廃止" else "#95a5a6")
            )
            st.markdown(
                f"## {name}"
                f"<span class='company-badge' style='background:{status_color}22;"
                f"color:{status_color};border:1px solid {status_color}66'>"
                f"{comp['market']}</span>",
                unsafe_allow_html=True,
            )

            # 上場企業：株価情報あり
            if comp["ticker"] and name in stocks and not stocks[name][0].empty:
                hist, info = stocks[name]
                render_stock_metrics(hist, info, period_label)
                st.divider()
                render_stock_tabs(hist, comp, period_label)
                st.divider()

            # データなし（上場廃止 or 非上場）
            elif comp["ticker"]:
                st.warning(f"{name} の株価データを取得できませんでした。")
                st.divider()
            else:
                st.info(
                    f"**{name}** は{comp['market']}のため株価データはありません。  \n"
                    "ニュース・IR 情報のみ表示します。"
                )
                st.divider()

            # ニュース（全社共通）
            st.markdown("### ニュース・IR 情報")
            render_news(comp)

    # ── フッター ────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "⚠️ このアプリは情報提供のみを目的としています。"
        "投資判断の参考にする場合は、必ず公式情報をご確認ください。"
    )
    st.caption(
        "データソース: Yahoo Finance (yfinance) ／ Google News RSS ／ 各社 IR・ニュースページ  \n"
        "カオナビは東証グロース上場後に非公開化（上場廃止）。SmartHR・HRブレインは非上場企業。"
    )


if __name__ == "__main__":
    main()
