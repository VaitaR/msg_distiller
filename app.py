#!/usr/bin/env python3
"""
Streamlit Dashboard for Event Manager.

Clean read-only frontend for viewing extracted events from Slack (internal)
and Telegram (external/market) sources.
"""

from datetime import UTC, datetime, timedelta
from typing import Final

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.adapters.repository_factory import create_repository
from src.config.settings import get_settings
from src.domain.protocols import RepositoryProtocol

# ============================================================================
# CONSTANTS
# ============================================================================

MAX_TITLE_LENGTH: Final[int] = 80
MAX_SUMMARY_LENGTH: Final[int] = 150

# Category colors for consistent styling
CATEGORY_COLORS: Final[dict[str, str]] = {
    "product": "#2ECC71",   # Green
    "risk": "#E74C3C",      # Red
    "process": "#3498DB",   # Blue
    "marketing": "#9B59B6", # Purple
    "org": "#F39C12",       # Orange
    "unknown": "#95A5A6",   # Gray
}

STATUS_COLORS: Final[dict[str, str]] = {
    "planned": "#BDC3C7",    # Light gray
    "confirmed": "#85C1E9",  # Light blue
    "started": "#F1C40F",    # Yellow
    "completed": "#27AE60",  # Green
    "postponed": "#E67E22",  # Orange
    "canceled": "#E74C3C",   # Red
    "rolled_back": "#8E44AD", # Purple
    "updated": "#3498DB",    # Blue
}


# ============================================================================
# DATA ACCESS
# ============================================================================

@st.cache_resource
def get_repository() -> RepositoryProtocol:
    """Get cached repository instance."""
    settings = get_settings()
    return create_repository(settings)


@st.cache_data(ttl=30)
def fetch_events_by_source(source_id: str, limit: int = 500) -> pd.DataFrame:
    """Fetch events filtered by source and convert to DataFrame."""
    repo = get_repository()
    
    # Get events from last 90 days to future
    start_date = datetime.now(UTC) - timedelta(days=90)
    end_date = datetime.now(UTC) + timedelta(days=365)
    
    all_events = repo.get_events_in_window(start_date, end_date)
    
    # Filter by source
    events = [e for e in all_events if e.source_id.value == source_id][:limit]
    
    if not events:
        return pd.DataFrame()
    
    data = []
    for evt in events:
        data.append({
            "event_id": str(evt.event_id)[:8],
            "title": evt.title[:MAX_TITLE_LENGTH] + "..." if len(evt.title) > MAX_TITLE_LENGTH else evt.title,
            "full_title": evt.title,
            "category": evt.category.value,
            "status": evt.status.value,
            "event_date": evt.event_date,
            "confidence": evt.confidence,
            "importance": evt.importance,
            "summary": (evt.summary[:MAX_SUMMARY_LENGTH] + "...") if evt.summary and len(evt.summary) > MAX_SUMMARY_LENGTH else (evt.summary or ""),
            "full_summary": evt.summary or "",
            "environment": evt.environment.value if evt.environment else "unknown",
            "source_id": evt.source_id.value,
            "links": evt.links[:3] if evt.links else [],
            "change_type": evt.change_type.value if evt.change_type else "other",
        })
    
    df = pd.DataFrame(data)
    
    # Ensure event_date is datetime
    if "event_date" in df.columns:
        df["event_date"] = pd.to_datetime(df["event_date"], utc=True)
    
    return df


# ============================================================================
# FILTER COMPONENTS
# ============================================================================

def render_filters(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Render filter controls and return filtered DataFrame."""
    
    if df.empty:
        return df
    
    # Create filter columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Category filter
        categories = ["All"] + sorted(df["category"].unique().tolist())
        selected_category = st.selectbox(
            "📂 Category",
            options=categories,
            key=f"{key_prefix}_category"
        )
    
    with col2:
        # Status filter
        statuses = ["All"] + sorted(df["status"].unique().tolist())
        selected_status = st.selectbox(
            "📊 Status",
            options=statuses,
            key=f"{key_prefix}_status"
        )
    
    with col3:
        # Importance filter
        min_importance = st.slider(
            "⭐ Min Importance",
            min_value=0,
            max_value=100,
            value=0,
            key=f"{key_prefix}_importance"
        )
    
    with col4:
        # Confidence filter
        min_confidence = st.slider(
            "🎯 Min Confidence",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.1,
            key=f"{key_prefix}_confidence"
        )
    
    # Second row: search and date range
    col5, col6 = st.columns([2, 2])
    
    with col5:
        search_query = st.text_input(
            "🔍 Search in titles",
            placeholder="Type to search...",
            key=f"{key_prefix}_search"
        )
    
    with col6:
        # Date range filter
        if df["event_date"].notna().any():
            min_date = df["event_date"].min().date()
            max_date = df["event_date"].max().date()
            
            date_range = st.date_input(
                "📅 Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key=f"{key_prefix}_date_range"
            )
        else:
            date_range = None
    
    # Apply filters
    filtered_df = df.copy()
    
    if selected_category != "All":
        filtered_df = filtered_df[filtered_df["category"] == selected_category]
    
    if selected_status != "All":
        filtered_df = filtered_df[filtered_df["status"] == selected_status]
    
    filtered_df = filtered_df[filtered_df["importance"] >= min_importance]
    filtered_df = filtered_df[filtered_df["confidence"] >= min_confidence]
    
    if search_query:
        mask = filtered_df["full_title"].str.contains(search_query, case=False, na=False)
        filtered_df = filtered_df[mask]
    
    if date_range and len(date_range) == 2 and filtered_df["event_date"].notna().any():
        start, end = date_range
        # Convert to datetime for comparison
        start_dt = pd.Timestamp(start, tz="UTC")
        end_dt = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        mask = (filtered_df["event_date"] >= start_dt) & (filtered_df["event_date"] < end_dt)
        filtered_df = filtered_df[mask]
    
    return filtered_df


# ============================================================================
# TABLE COMPONENTS
# ============================================================================

def render_events_table(df: pd.DataFrame, key_prefix: str) -> None:
    """Render events table with proper column configuration."""
    
    if df.empty:
        st.info("No events match the selected filters.")
        return
    
    # Show count
    st.caption(f"Showing {len(df)} events")
    
    # Prepare display DataFrame
    display_df = df[[
        "title", "category", "status", "event_date", 
        "importance", "confidence", "environment", "change_type"
    ]].copy()
    
    # Format date for display
    display_df["event_date"] = display_df["event_date"].dt.strftime("%Y-%m-%d %H:%M")
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "title": st.column_config.TextColumn(
                "📌 Title",
                width="large",
                help="Event title"
            ),
            "category": st.column_config.TextColumn(
                "📂 Category",
                width="small",
            ),
            "status": st.column_config.TextColumn(
                "📊 Status",
                width="small",
            ),
            "event_date": st.column_config.TextColumn(
                "📅 Date",
                width="medium",
            ),
            "importance": st.column_config.ProgressColumn(
                "⭐ Importance",
                min_value=0,
                max_value=100,
                format="%d",
            ),
            "confidence": st.column_config.ProgressColumn(
                "🎯 Confidence",
                min_value=0,
                max_value=1,
                format="%.1f",
            ),
            "environment": st.column_config.TextColumn(
                "🌍 Env",
                width="small",
            ),
            "change_type": st.column_config.TextColumn(
                "🔄 Type",
                width="small",
            ),
        },
    )


def render_metrics(df: pd.DataFrame, source_name: str) -> None:
    """Render summary metrics for events."""
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📊 Total", len(df))
    
    with col2:
        risk_count = len(df[df["category"] == "risk"]) if not df.empty else 0
        st.metric("🚨 Risks", risk_count)
    
    with col3:
        product_count = len(df[df["category"] == "product"]) if not df.empty else 0
        st.metric("🚀 Product", product_count)
    
    with col4:
        active_count = len(df[df["status"].isin(["started", "planned"])]) if not df.empty else 0
        st.metric("⚡ Active", active_count)
    
    with col5:
        avg_importance = df["importance"].mean() if not df.empty else 0
        st.metric("⭐ Avg Importance", f"{avg_importance:.0f}")


# ============================================================================
# TIMELINE COMPONENT (Simple and Working)
# ============================================================================

def render_timeline(df: pd.DataFrame, key_prefix: str) -> None:
    """Render timeline visualization using px.timeline (Gantt-style)."""
    
    if df.empty or df["event_date"].isna().all():
        st.info("No events with dates to display on timeline.")
        return
    
    # Filter events with valid dates
    chart_df = df[df["event_date"].notna()].copy()
    
    if chart_df.empty:
        st.info("No events with dates to display on timeline.")
        return
    
    # Category filter
    available_categories = sorted(chart_df["category"].unique().tolist())
    selected_categories = st.multiselect(
        "📂 Filter by category",
        options=available_categories,
        default=available_categories,
        key=f"{key_prefix}_timeline_categories",
    )
    
    if not selected_categories:
        st.warning("Select at least one category to display.")
        return
    
    chart_df = chart_df[chart_df["category"].isin(selected_categories)]
    
    # Sort by date
    chart_df = chart_df.sort_values("event_date", ascending=False)
    
    # Limit to avoid overloading
    if len(chart_df) > 30:
        st.caption(f"Showing top 30 events out of {len(chart_df)}")
        chart_df = chart_df.head(30)
    
    # Create proper start/end for Gantt
    chart_df["Start"] = chart_df["event_date"]
    chart_df["End"] = chart_df["event_date"] + pd.Timedelta(days=1)
    chart_df["Task"] = chart_df["title"].str[:60]
    
    # Create Gantt chart
    fig = px.timeline(
        chart_df,
        x_start="Start",
        x_end="End",
        y="Task",
        color="category",
        color_discrete_map=CATEGORY_COLORS,
        hover_data=["status", "importance", "confidence"],
        title="📅 Events Timeline",
    )
    
    # Add TODAY marker
    today = datetime.now(UTC)
    fig.add_vline(
        x=today.timestamp() * 1000,  # Convert to milliseconds for plotly
        line_dash="dash",
        line_color="red",
        line_width=2,
        annotation_text="TODAY",
        annotation_position="top",
    )
    
    fig.update_layout(
        height=max(400, len(chart_df) * 28),
        xaxis_title="",
        yaxis_title="",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    
    fig.update_yaxes(automargin=True, tickfont=dict(size=11))
    
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_timeline")


# ============================================================================
# CALENDAR VIEW COMPONENT
# ============================================================================

def render_calendar_view(df: pd.DataFrame, key_prefix: str) -> None:
    """Render calendar view similar to Google Calendar."""
    
    if df.empty or df["event_date"].isna().all():
        st.info("No events with dates to display.")
        return
    
    chart_df = df[df["event_date"].notna()].copy()
    
    if chart_df.empty:
        st.info("No events with dates to display.")
        return
    
    # Get date range
    min_date = chart_df["event_date"].min()
    max_date = chart_df["event_date"].max()
    
    # Date navigation
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Month selector
        today = datetime.now(UTC)
        available_months = pd.date_range(
            start=min_date.replace(day=1),
            end=max_date.replace(day=1) + pd.DateOffset(months=1),
            freq='MS'
        )
        month_options = [d.strftime("%B %Y") for d in available_months]
        current_month_str = today.strftime("%B %Y")
        default_idx = month_options.index(current_month_str) if current_month_str in month_options else 0
        
        selected_month = st.selectbox(
            "📅 Select Month",
            options=month_options,
            index=default_idx,
            key=f"{key_prefix}_calendar_month"
        )
    
    # Parse selected month
    selected_date = pd.to_datetime(selected_month, format="%B %Y")
    month_start = selected_date.replace(day=1, tzinfo=UTC)
    month_end = (month_start + pd.DateOffset(months=1) - pd.Timedelta(days=1)).replace(tzinfo=UTC)
    
    # Filter events for selected month
    month_events = chart_df[
        (chart_df["event_date"] >= month_start) & 
        (chart_df["event_date"] <= month_end)
    ]
    
    # Create calendar grid
    st.markdown("---")
    
    # Day headers
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cols = st.columns(7)
    for i, day in enumerate(days):
        cols[i].markdown(f"**{day}**")
    
    # Get first day of month and calculate offset
    first_day = month_start
    first_weekday = first_day.weekday()  # Monday = 0
    
    # Calculate total days in month
    days_in_month = (month_end - month_start).days + 1
    
    # Create weeks
    current_day = 1
    week_num = 0
    
    while current_day <= days_in_month:
        cols = st.columns(7)
        
        for weekday in range(7):
            # Skip days before month starts
            if week_num == 0 and weekday < first_weekday:
                cols[weekday].write("")
                continue
            
            if current_day > days_in_month:
                cols[weekday].write("")
                continue
            
            # Current date
            current_date = month_start + pd.Timedelta(days=current_day - 1)
            
            # Get events for this day
            day_events = month_events[
                month_events["event_date"].dt.date == current_date.date()
            ]
            
            # Build day cell content
            is_today = current_date.date() == today.date()
            day_style = "🔴 " if is_today else ""
            
            with cols[weekday]:
                # Day number
                if is_today:
                    st.markdown(f"**{day_style}{current_day}**")
                else:
                    st.markdown(f"**{current_day}**")
                
                # Events for this day
                for _, event in day_events.iterrows():
                    cat_emoji = {
                        "product": "🚀",
                        "risk": "🚨",
                        "process": "⚙️",
                        "marketing": "📣",
                        "org": "👥",
                        "unknown": "❓"
                    }.get(event["category"], "📌")
                    
                    # Truncate title for display
                    title_short = event["title"][:12] + "…" if len(event["title"]) > 12 else event["title"]
                    
                    # Use native Streamlit popover
                    with st.popover(f"{cat_emoji} {title_short}", use_container_width=True):
                        st.markdown(f"**{event['full_title']}**")
                        st.caption(f"📂 {event['category'].title()} | 📊 {event['status'].title()}")
                        st.caption(f"⭐ Importance: {event['importance']} | 🎯 Confidence: {event['confidence']:.0%}")
                        st.markdown("---")
                        st.write(event['summary'][:200] + "..." if len(str(event['summary'])) > 200 else event['summary'])
            
            current_day += 1
        
        week_num += 1
    
    # Legend
    st.markdown("---")
    legend_items = " | ".join([
        f"{emoji} {cat.title()}"
        for cat, emoji in {
            "product": "🚀",
            "risk": "🚨", 
            "process": "⚙️",
            "marketing": "📣",
            "org": "👥",
        }.items()
    ])
    st.caption(f"Legend: {legend_items}")
    
    # Summary
    st.caption(f"📊 {len(month_events)} events in {selected_month}")


# ============================================================================
# EVENT LIST VIEW
# ============================================================================

def render_event_list(df: pd.DataFrame, key_prefix: str) -> None:
    """Render events as a list grouped by date."""
    
    if df.empty or df["event_date"].isna().all():
        st.info("No events to display.")
        return
    
    chart_df = df[df["event_date"].notna()].copy()
    chart_df = chart_df.sort_values("event_date", ascending=False)
    
    # Group by date
    chart_df["date_str"] = chart_df["event_date"].dt.strftime("%A, %B %d, %Y")
    
    for date_str, group in chart_df.groupby("date_str", sort=False):
        st.markdown(f"### 📅 {date_str}")
        
        for _, event in group.iterrows():
            cat_color = CATEGORY_COLORS.get(event["category"], "#95A5A6")
            cat_emoji = {
                "product": "🚀",
                "risk": "🚨",
                "process": "⚙️",
                "marketing": "📣",
                "org": "👥",
                "unknown": "❓"
            }.get(event["category"], "📌")
            
            status_emoji = {
                "planned": "📋",
                "started": "▶️",
                "completed": "✅",
                "canceled": "❌",
            }.get(event["status"], "📌")
            
            with st.container():
                st.markdown(
                    f'<div style="background-color:{cat_color}15; '
                    f'border-left:4px solid {cat_color}; '
                    f'padding:10px 15px; margin:5px 0; border-radius:4px;">'
                    f'<div style="font-size:16px; font-weight:600;">{cat_emoji} {event["full_title"]}</div>'
                    f'<div style="font-size:13px; color:#888; margin-top:4px;">'
                    f'{status_emoji} {event["status"].title()} | '
                    f'⭐ {event["importance"]} | '
                    f'🎯 {event["confidence"]:.0%}'
                    f'</div>'
                    f'<div style="font-size:12px; color:#666; margin-top:4px;">{event["summary"][:150]}...</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        
        st.markdown("")


# ============================================================================
# CATEGORY DISTRIBUTION CHART
# ============================================================================

def render_category_chart(df: pd.DataFrame, key_prefix: str) -> None:
    """Render category distribution pie chart."""
    
    if df.empty:
        return
    
    category_counts = df["category"].value_counts()
    
    fig = px.pie(
        values=category_counts.values,
        names=category_counts.index,
        title="Distribution by Category",
        color=category_counts.index,
        color_discrete_map=CATEGORY_COLORS,
        hole=0.4,
    )
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
    )
    
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_pie")


def render_status_chart(df: pd.DataFrame, key_prefix: str) -> None:
    """Render status distribution bar chart."""
    
    if df.empty:
        return
    
    status_counts = df["status"].value_counts()
    
    fig = px.bar(
        x=status_counts.values,
        y=status_counts.index,
        orientation="h",
        title="Distribution by Status",
        color=status_counts.index,
        color_discrete_map=STATUS_COLORS,
    )
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
        xaxis_title="Count",
        yaxis_title="",
    )
    
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_bar")


# ============================================================================
# SOURCE TABS
# ============================================================================

def render_source_tab(source_id: str, source_name: str, source_emoji: str, description: str) -> None:
    """Render complete tab for a single source."""
    
    st.markdown(f"### {source_emoji} {source_name}")
    st.caption(description)
    
    # Fetch data
    df = fetch_events_by_source(source_id)
    
    if df.empty:
        st.warning(f"No events found from {source_name}.")
        return
    
    # Metrics row
    render_metrics(df, source_name)
    
    st.divider()
    
    # Filters
    st.markdown("#### 🎛️ Filters")
    filtered_df = render_filters(df, key_prefix=source_id)
    
    st.divider()
    
    # Sub-tabs for table and visualizations
    tab_table, tab_timeline, tab_calendar, tab_list, tab_analytics = st.tabs([
        "📋 Table", 
        "📊 Timeline",
        "📅 Calendar",
        "📝 List",
        "📈 Analytics"
    ])
    
    with tab_table:
        render_events_table(filtered_df, key_prefix=source_id)
    
    with tab_timeline:
        render_timeline(filtered_df, key_prefix=source_id)
    
    with tab_calendar:
        render_calendar_view(filtered_df, key_prefix=source_id)
    
    with tab_list:
        render_event_list(filtered_df, key_prefix=source_id)
    
    with tab_analytics:
        col1, col2 = st.columns(2)
        with col1:
            render_category_chart(filtered_df, key_prefix=source_id)
        with col2:
            render_status_chart(filtered_df, key_prefix=source_id)


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    
    # Page configuration
    st.set_page_config(
        page_title="Event Manager",
        page_icon="📅",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .source-header {
        font-size: 1.5rem;
        margin-top: 1rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.1rem;
        font-weight: 500;
    }
    
    /* Tooltip styles for calendar events */
    .event-item {
        position: relative;
        background-color: rgba(46, 204, 113, 0.125);
        border-left: 3px solid;
        padding: 2px 4px;
        margin: 1px 0;
        font-size: 11px;
        border-radius: 2px;
        overflow: hidden;
        white-space: nowrap;
        cursor: pointer;
    }
    
    .event-item .tooltip-text {
        visibility: hidden;
        position: absolute;
        z-index: 1000;
        bottom: 125%;
        left: 50%;
        transform: translateX(-50%);
        background-color: rgba(0, 0, 0, 0.95);
        color: #fff;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 12px;
        white-space: normal;
        width: 280px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        line-height: 1.4;
    }
    
    .event-item .tooltip-text::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -5px;
        border-width: 5px;
        border-style: solid;
        border-color: rgba(0, 0, 0, 0.95) transparent transparent transparent;
    }
    
    .event-item:hover .tooltip-text {
        visibility: visible;
        opacity: 1;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">📅 Event Manager Dashboard</h1>', unsafe_allow_html=True)
    st.caption("Centralized view of internal (Slack) and external (Telegram) events")
    
    # Sidebar with system info
    with st.sidebar:
        st.header("ℹ️ System Info")
        
        settings = get_settings()
        
        # Database info
        if settings.database_type == "postgres":
            st.success(f"🐘 PostgreSQL: {settings.postgres_database}")
        else:
            st.info(f"📁 SQLite: {settings.db_path}")
        
        # Quick stats
        st.divider()
        st.subheader("📊 Quick Stats")
        
        slack_df = fetch_events_by_source("slack")
        telegram_df = fetch_events_by_source("telegram")
        
        st.metric("Slack Events", len(slack_df))
        st.metric("Telegram Events", len(telegram_df))
        st.metric("Total Events", len(slack_df) + len(telegram_df))
        
        # Refresh button
        st.divider()
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # Main content - source tabs
    tab_slack, tab_telegram, tab_all = st.tabs([
        "🏢 Internal Events (Slack)",
        "🌍 External Events (Telegram)",
        "📊 All Events"
    ])
    
    with tab_slack:
        render_source_tab(
            source_id="slack",
            source_name="Internal Events",
            source_emoji="🏢",
            description="Events from internal Slack channels: releases, deployments, incidents, team updates"
        )
    
    with tab_telegram:
        render_source_tab(
            source_id="telegram",
            source_name="External Events", 
            source_emoji="🌍",
            description="Events from Telegram channels: market news, competitor updates, industry trends"
        )
    
    with tab_all:
        st.markdown("### 📊 All Events Combined")
        st.caption("Overview of all events from both sources")
        
        # Combine both sources
        slack_df = fetch_events_by_source("slack")
        telegram_df = fetch_events_by_source("telegram")
        
        if slack_df.empty and telegram_df.empty:
            st.warning("No events found in any source.")
            return
        
        combined_df = pd.concat([slack_df, telegram_df], ignore_index=True)
        
        # Metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("📊 Total", len(combined_df))
        with col2:
            st.metric("🏢 Slack", len(slack_df))
        with col3:
            st.metric("🌍 Telegram", len(telegram_df))
        with col4:
            risk_count = len(combined_df[combined_df["category"] == "risk"])
            st.metric("🚨 Risks", risk_count)
        with col5:
            avg_imp = combined_df["importance"].mean() if not combined_df.empty else 0
            st.metric("⭐ Avg Importance", f"{avg_imp:.0f}")
        
        st.divider()
        
        # Filters
        st.markdown("#### 🎛️ Filters")
        filtered_df = render_filters(combined_df, key_prefix="all")
        
        st.divider()
        
        # Content tabs
        tab_table, tab_timeline, tab_calendar, tab_list, tab_analytics = st.tabs([
            "📋 Table",
            "📊 Timeline",
            "📅 Calendar",
            "📝 List",
            "📈 Analytics"
        ])
        
        with tab_table:
            render_events_table(filtered_df, key_prefix="all")
        
        with tab_timeline:
            render_timeline(filtered_df, key_prefix="all")
        
        with tab_calendar:
            render_calendar_view(filtered_df, key_prefix="all")
        
        with tab_list:
            render_event_list(filtered_df, key_prefix="all")
        
        with tab_analytics:
            col1, col2 = st.columns(2)
            with col1:
                render_category_chart(filtered_df, key_prefix="all")
            with col2:
                render_status_chart(filtered_df, key_prefix="all")


if __name__ == "__main__":
    main()
