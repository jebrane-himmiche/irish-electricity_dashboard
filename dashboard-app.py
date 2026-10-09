from __future__ import annotations

import io
# import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from io import BytesIO
# from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(
    page_title="Irish Home Energy Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

COLORS = {
    "cyan": "#22D3EE", "blue": "#3B82F6", "violet": "#8B5CF6",
    "pink": "#EC4899", "orange": "#F97316", "green": "#10B981",
    "yellow": "#FACC15", "red": "#EF4444", "bg": "#070B14",
    "card": "#111827", "text": "#F8FAFC", "muted": "#94A3B8",
}
CHART_COLORS = [COLORS[k] for k in ("cyan", "violet", "pink", "orange", "green", "yellow", "blue")]
px.defaults.template = "plotly_dark"
px.defaults.color_discrete_sequence = CHART_COLORS

st.markdown(
    """
<style>
.stApp {background: radial-gradient(circle at top left,#15213b 0,#070b14 38%,#05070d 100%); color:#f8fafc;}
.block-container {max-width:1500px; padding-top:1.15rem; padding-bottom:3rem;}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#0d1424,#080c15); border-right:1px solid #263244;}
[data-testid="stSidebar"] * {color:#e5edf8;}
.hero {padding:28px 30px; border-radius:22px; margin-bottom:20px; background:linear-gradient(125deg,#0f766e 0%,#1d4ed8 45%,#7c3aed 100%); box-shadow:0 18px 55px rgba(29,78,216,.26);}
.hero h1 {color:white!important; margin:0; font-size:2.35rem; letter-spacing:-.035em;}
.hero p {color:#eaf5ff!important; margin:.55rem 0 0; font-size:1.02rem;}
.section {font-weight:800; font-size:1.25rem; margin:1.4rem 0 .7rem; color:#f8fafc;}
[data-testid="stMetric"] {background:linear-gradient(155deg,rgba(30,41,59,.95),rgba(15,23,42,.95)); border:1px solid #334155; border-radius:18px; padding:17px; min-height:128px; box-shadow:0 10px 30px rgba(0,0,0,.22);}
[data-testid="stMetricLabel"] {color:#a5b4c7!important; font-weight:650;}
[data-testid="stMetricValue"] {color:#fff!important; font-weight:800; font-size:1.65rem;}
[data-testid="stMetricDelta"] {color:#67e8f9!important;}
div[data-testid="stPlotlyChart"] {background:rgba(15,23,42,.82); border:1px solid #263449; border-radius:18px; padding:8px; box-shadow:0 10px 25px rgba(0,0,0,.16);}
.stButton>button,.stDownloadButton>button {border-radius:12px; border:1px solid #2563eb; background:linear-gradient(90deg,#2563eb,#7c3aed); color:white; font-weight:700;}
h1,h2,h3,p,label,span {color:#f8fafc;}
.note {color:#94a3b8; font-size:.88rem;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """<div class="hero"><h1>⚡ Irish Home Energy Dashboard</h1>
    <p>Household electricity consumption from 30-minute ESB smart-meter readings</p></div>""",
    unsafe_allow_html=True,
)

REQUIRED_COLUMNS = {"Read Value", "Read Date and End Time"}


@st.cache_data(show_spinner=False)
def load_csv(file_bytes: bytes) -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(io.BytesIO(file_bytes))
    raw.columns = raw.columns.str.strip()
    missing = REQUIRED_COLUMNS.difference(raw.columns)
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(sorted(missing)))

    df = raw.copy()
    # Handles the mixed day-first formats in ESB exports, including D/M/YYYY and DD-MM-YYYY.
    df["timestamp"] = pd.to_datetime(
        df["Read Date and End Time"].astype(str).str.strip(),
        dayfirst=True,
        errors="coerce",
    )
    df["kwh"] = pd.to_numeric(df["Read Value"], errors="coerce")
    invalid_dates = int(df["timestamp"].isna().sum())
    invalid_values = int(df["kwh"].isna().sum())
    df = df.dropna(subset=["timestamp", "kwh"])
    df = df[df["kwh"] >= 0].copy()
    duplicate_rows = int(df.duplicated("timestamp").sum())

    # Consolidate duplicate timestamps safely before aggregating.
    df = df.groupby("timestamp", as_index=False)["kwh"].sum().sort_values("timestamp")
    df["kw"] = df["kwh"] * 2.0
    df["date"] = df["timestamp"].dt.floor("D")
    df["month"] = df["timestamp"].dt.to_period("M")
    df["weekday"] = df["timestamp"].dt.day_name()
    df["weekday_number"] = df["timestamp"].dt.dayofweek

    quality = {
        "raw_rows": len(raw), "valid_rows": len(df), "invalid_dates": invalid_dates,
        "invalid_values": invalid_values, "duplicate_timestamps": duplicate_rows,
    }
    return df, quality


def finish_figure(fig: go.Figure, title: str, y_title: str = "kWh") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=.025, xanchor="left", font=dict(size=20, color="#F8FAFC")),
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#DCE7F5"), hoverlabel=dict(bgcolor="#111827", font_color="white"),
        margin=dict(l=28, r=20, t=62, b=30), legend_title_text="",
    )
    fig.update_xaxes(showgrid=False, linecolor="#334155")
    fig.update_yaxes(title=y_title, gridcolor="rgba(148,163,184,.16)", zeroline=False)
    return fig


with st.sidebar:
    st.header("Dashboard controls")
    uploaded_file = st.file_uploader(
        "Upload an ESB smart-meter CSV",
        type=["csv"],
        help="Required columns: Read Value and Read Date and End Time.",
    )
    st.caption("The uploaded file is analysed in the current app session.")

if uploaded_file is None:
    st.info("Upload your electricity CSV using the sidebar to generate the dashboard.")
    st.stop()

try:
    all_data, quality = load_csv(uploaded_file.getvalue())
except Exception as exc:
    st.error(f"The CSV could not be processed: {exc}")
    st.stop()

if all_data.empty:
    st.error("The file contains no valid non-negative electricity readings.")
    st.stop()

with st.sidebar:
    min_date = all_data["timestamp"].min().date()
    max_date = all_data["timestamp"].max().date()
    selected_dates = st.date_input(
        "Chart date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
    show_average = st.checkbox("Show 7-day average", value=False)
    show_markers = st.checkbox("Show daily markers", value=False)
    include_partial_months = st.checkbox("Include partial months in monthly average", value=False)
    st.divider()
    st.caption(f"Available data: {min_date:%d %b %Y} to {max_date:%d %b %Y}")

if not isinstance(selected_dates, (tuple, list)) or len(selected_dates) != 2:
    st.warning("Select both a start date and an end date.")
    st.stop()

start_date, end_date = selected_dates
filtered = all_data[
    (all_data["timestamp"].dt.date >= start_date)
    & (all_data["timestamp"].dt.date <= end_date)
    ].copy()
if filtered.empty:
    st.warning("No readings exist in the selected date range.")
    st.stop()

# All-data metrics deliberately use the entire uploaded dataset. Charts use the selected range.
daily_all = all_data.groupby("date", as_index=False)["kwh"].sum()
monthly_all = all_data.groupby("month", as_index=False)["kwh"].sum()
latest_timestamp = all_data["timestamp"].max()
this_month_period = latest_timestamp.to_period("M")
last_month_period = this_month_period - 1
this_month_kwh = all_data.loc[all_data["month"] == this_month_period, "kwh"].sum()
last_month_kwh = all_data.loc[all_data["month"] == last_month_period, "kwh"].sum()

if include_partial_months:
    months_for_average = monthly_all
else:
    interval_counts = all_data.groupby("month").size()
    complete_months = []
    for month_period, count in interval_counts.items():
        expected = month_period.days_in_month * 48
        if count >= expected:
            complete_months.append(month_period)
    months_for_average = monthly_all[monthly_all["month"].isin(complete_months)]
    if months_for_average.empty:
        months_for_average = monthly_all

peak_index = all_data["kwh"].idxmax()
peak = all_data.loc[peak_index]
# "Average peak demand": average of each day's maximum half-hour demand.
daily_peak_kw = all_data.groupby("date")["kw"].max()
average_peak_demand = daily_peak_kw.mean()

st.markdown('<div class="section">Executive summary · Consumption</div>', unsafe_allow_html=True)
row1 = st.columns(4)
row1[0].metric("Total consumption · all data", f"{all_data['kwh'].sum():,.1f} kWh")
row1[1].metric("Consumption · latest month", f"{this_month_kwh:,.1f} kWh", str(this_month_period))
change = ((this_month_kwh - last_month_kwh) / last_month_kwh * 100) if last_month_kwh else None
row1[2].metric("Consumption · previous month", f"{last_month_kwh:,.1f} kWh", str(last_month_period))
row1[3].metric("Average daily consumption", f"{daily_all['kwh'].mean():,.2f} kWh/day")

row2 = st.columns(4)
row2[0].metric("Average monthly consumption", f"{months_for_average['kwh'].mean():,.1f} kWh/month")
max_day = daily_all.loc[daily_all["kwh"].idxmax()]
min_day = daily_all.loc[daily_all["kwh"].idxmin()]
row2[1].metric("Maximum daily consumption", f"{max_day['kwh']:,.2f} kWh", max_day["date"].strftime("%d %b %Y"))
row2[2].metric("Minimum daily consumption", f"{min_day['kwh']:,.2f} kWh", min_day["date"].strftime("%d %b %Y"))
row2[3].metric("Latest vs previous month", "N/A" if change is None else f"{change:+.1f}%")

st.markdown('<div class="section">Executive summary · Peak demand</div>', unsafe_allow_html=True)
row3 = st.columns(4)
row3[0].metric("Highest 30-minute consumption", f"{peak['kwh']:,.3f} kWh")
row3[1].metric("Highest estimated demand", f"{peak['kw']:,.2f} kW")
row3[2].metric("Peak date and time", peak["timestamp"].strftime("%d %b %Y"), peak["timestamp"].strftime("%H:%M"))
row3[3].metric("Average daily peak demand", f"{average_peak_demand:,.2f} kW")

st.caption(
    "Demand is the average power during a 30-minute interval: kW = interval kWh × 2. Average peak demand is the mean of each day's maximum interval demand.")

# Selected-range series for charts.
daily = filtered.groupby("date", as_index=False)["kwh"].sum()
daily["7-day average"] = daily["kwh"].rolling(7, min_periods=1).mean()
monthly = filtered.groupby("month", as_index=False)["kwh"].sum()
monthly["Month"] = monthly["month"].astype(str)
daily["cumulative_kwh"] = daily["kwh"].cumsum()
weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
weekday = filtered.groupby(["weekday", "weekday_number"], as_index=False)["kwh"].sum().sort_values("weekday_number")
weekday["Average daily kWh"] = weekday["kwh"] / filtered.groupby("weekday")["date"].nunique().reindex(
    weekday["weekday"]).to_numpy()

st.markdown('<div class="section">Most important charts</div>', unsafe_allow_html=True)

# Chart 1: daily trend
trend = go.Figure()
trend.add_trace(go.Scatter(
    x=daily["date"], y=daily["kwh"], name="Daily consumption",
    mode="lines+markers" if show_markers else "lines",
    line=dict(color=COLORS["cyan"], width=2.5), marker=dict(size=5),
    fill="tozeroy", fillcolor="rgba(34,211,238,.10)",
))
if show_average:
    trend.add_trace(go.Scatter(
        x=daily["date"], y=daily["7-day average"], name="7-day average",
        mode="lines", line=dict(color=COLORS["pink"], width=3),
    ))
st.plotly_chart(finish_figure(trend, "Daily consumption trend"), use_container_width=True)

left, right = st.columns(2)
monthly_fig = px.bar(
    monthly, x="Month", y="kwh", text_auto=".1f",
    color="kwh", color_continuous_scale=[COLORS["blue"], COLORS["violet"], COLORS["pink"]],
)
monthly_fig.update_coloraxes(showscale=False)
left.plotly_chart(finish_figure(monthly_fig, "Monthly consumption"), use_container_width=True)

cumulative_fig = go.Figure(go.Scatter(
    x=daily["date"], y=daily["cumulative_kwh"], mode="lines",
    line=dict(color=COLORS["green"], width=3), fill="tozeroy",
    fillcolor="rgba(16,185,129,.16)", name="Cumulative consumption",
))
right.plotly_chart(finish_figure(cumulative_fig, "Cumulative consumption", "Cumulative kWh"), use_container_width=True)

weekday_fig = px.bar(
    weekday, x="weekday", y="Average daily kWh", color="Average daily kWh",
    category_orders={"weekday": weekday_order},
    color_continuous_scale=[COLORS["green"], COLORS["yellow"], COLORS["orange"], COLORS["red"]],
    text_auto=".1f",
)
weekday_fig.update_coloraxes(showscale=False)
st.plotly_chart(finish_figure(weekday_fig, "Average daily consumption by day of week", "Average kWh/day"),
                use_container_width=True)

with st.expander("Data quality and calculation notes"):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw CSV rows", f"{quality['raw_rows']:,}")
    c2.metric("Valid intervals", f"{quality['valid_rows']:,}")
    c3.metric("Invalid dates removed", f"{quality['invalid_dates']:,}")
    c4.metric("Duplicate timestamps combined", f"{quality['duplicate_timestamps']:,}")
    st.write(
        "The month cards use the latest month found in the uploaded CSV, rather than the computer's current calendar month. This prevents an older ESB export from showing zero unexpectedly.")

export = filtered[["timestamp", "kwh", "kw", "weekday"]].copy()
st.download_button(
    "⬇️ Download filtered readings",
    data=export.to_csv(index=False).encode("utf-8"),
    file_name="filtered_electricity_readings.csv",
    mime="text/csv",
    use_container_width=True,
)
st.markdown(
    '<p class="note">This dashboard analyses imported grid electricity only. It cannot identify individual appliances or calculate supplier bills from this CSV alone.</p>',
    unsafe_allow_html=True)


#### PDF

def generate_pdf_report(
        total_consumption,
        this_month,
        last_month,
        avg_daily,
        avg_monthly,
        max_daily,
        min_daily,
        peak_kwh,
        peak_kw,
        peak_datetime,
        avg_peak_kw,
):
    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4
    )

    styles = getSampleStyleSheet()

    elements = []

    title = Paragraph(
        "Irish Home Energy Dashboard Report",
        styles["Title"]
    )

    elements.append(title)
    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Executive Summary Metrics",
            styles["Heading1"]
        )
    )

    metrics = [
        f"Total Consumption: {total_consumption:.2f} kWh",
        f"Consumption This Month: {this_month:.2f} kWh",
        f"Consumption Last Month: {last_month:.2f} kWh",
        f"Average Daily Consumption: {avg_daily:.2f} kWh/day",
        f"Average Monthly Consumption: {avg_monthly:.2f} kWh/month",
        f"Maximum Daily Consumption: {max_daily:.2f} kWh",
        f"Minimum Daily Consumption: {min_daily:.2f} kWh",
        f"Highest 30-minute Consumption: {peak_kwh:.2f} kWh",
        f"Highest Demand: {peak_kw:.2f} kW",
        f"Peak Time: {peak_datetime}",
        f"Average Peak Demand: {avg_peak_kw:.2f} kW",
    ]

    for item in metrics:
        elements.append(
            Paragraph(item, styles["BodyText"])
        )

    pdf.build(elements)

    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data


pdf_bytes = generate_pdf_report(
    total_consumption=all_data["kwh"].sum(),
    this_month=this_month_kwh,
    last_month=last_month_kwh,
    avg_daily=daily_all["kwh"].mean(),
    avg_monthly=monthly_all["kwh"].mean(),
    max_daily=max_day["kwh"],
    min_daily=min_day["kwh"],
    peak_kwh=peak["kwh"],
    peak_kw=peak["kw"],
    peak_datetime=peak["timestamp"].strftime("%d-%m-%Y %H:%M"),
    avg_peak_kw=average_peak_demand,
)

st.download_button(
    label="📄 Download PDF Report",
    data=pdf_bytes,
    file_name="electricity_report.pdf",
    mime="application/pdf",
    use_container_width=True
)
