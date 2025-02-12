# Version 1.5.5
import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import pytz
from geopy.geocoders import Nominatim
import jinja2
import base64
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from ratelimit import limits, sleep_and_retry
import threading
from xhtml2pdf import pisa
import os

# --- Rate Limiter and Helper Functions -------------------------------------

class ThreadSafeRateLimiter:
    def __init__(self, calls_per_second=1):
        self.calls_per_second = calls_per_second
        self.last_call = time.time()
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            time_to_wait = max(0, (1.0 / self.calls_per_second) - (now - self.last_call))
            if time_to_wait > 0:
                time.sleep(time_to_wait)
            self.last_call = time.time()

geocoding_limiter = ThreadSafeRateLimiter(calls_per_second=1)

@sleep_and_retry
@limits(calls=5, period=1)
def rate_limited_api_call(base_url, params):
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    return response.json()

def validate_location(location):
    """Validate if a location exists using GeoPy."""
    geolocator = Nominatim(user_agent="seo_analysis_tool")
    try:
        if isinstance(location, str) and location.isdigit() and len(location) == 5:
            search_term = f"{location}, USA"
        else:
            search_term = f"{location['city']}, {location['state']}, USA"

        geocoding_limiter.wait()
        location_data = geolocator.geocode(search_term)
        return True if location_data else False
    except:
        return False

def fetch_serp_data(query, api_key):
    base_url = "https://api.valueserp.com/search"
    params = {
        'api_key': api_key,
        'q': query['query'],
        'location': query['location'],
        'google_domain': 'google.com',
        'gl': 'us',
        'hl': 'en',
        'num': 10,
        'output': 'json'
    }
    try:
        return rate_limited_api_call(base_url, params)
    except requests.exceptions.RequestException:
        return None

def process_query(query, target_url, api_key):
    serp_data = fetch_serp_data(query, api_key)
    if not serp_data:
        return None

    organic_results = serp_data.get('organic_results', [])
    local_results = serp_data.get('local_results', [])

    position = "Not on Page 1"
    for idx, result in enumerate(organic_results, 1):
        if target_url in result.get('domain', '').lower():
            position = f"#{idx}"
            break

    return {
        'keyword': query['keyword'],
        'location': query['location'],
        'target_position': position,
        'organic_results': organic_results[:3],
        'local_results': local_results[:3]
    }

def parallel_process_queries(search_queries, target_url, progress_text, progress_bar, api_key):
    """Process queries in parallel with progress tracking."""
    results = []
    completed = 0
    total = len(search_queries)
    lock = threading.Lock()

    def update_progress():
        nonlocal completed
        with lock:
            completed += 1
            progress = completed / total
            progress_bar.progress(progress)
            progress_text.text(f"Processed {completed}/{total} queries...")

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_query = {
            executor.submit(process_query, query, target_url, api_key): query
            for query in search_queries
        }
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                st.warning(f"Error processing query '{query['keyword']}' in {query['location']}: {str(e)}")
            update_progress()

    return results


# --- Generate PDF (No "By Chris Walnum," No TOC) ---------------------------

def generate_html_report(results, target_url, client_logo_base64=None):
    """
    Generates a PDF/HTML report WITHOUT "By Chris Walnum" text
    and WITHOUT a <pdf:toc> element, so no table of contents page
    appears at the end.
    """

    template_string = r"""
<!DOCTYPE html>
<html xmlns:pdf="http://ns.adobe.com/xdp/pdf/">
<head>
    <meta charset="UTF-8"/>
    <title>SEO Analysis Report</title>
    <style>
        @page {
            margin: 2cm;
        }
        body {
            font-family: Arial, sans-serif;
            color: #1a1a1a;
            margin: 0;
            padding: 0;
        }

        /* Cover Page */
        .cover-page {
            text-align: center;
            margin-top: 20px;
            page-break-after: always;
        }
        .cover-logo {
            margin-bottom: 8px;
        }
        .cover-title {
            font-size: 26px;
            color: #2563eb;
            margin: 6px 0;
        }
        /* We do NOT include "By Chris Walnum" here. */
        .domain-line,
        .timestamp-line {
            color: #333;
            font-size: 12px;
            margin: 0;
        }

        .summaries-row {
            display: flex;
            justify-content: center;
            align-items: flex-start;
            gap: 60px;
            margin-top: 15px;
        }
        .summary-block {
            width: 270px;
        }
        .summary-title {
            font-size: 16px;
            color: #2563eb;
            margin-bottom: 8px;
        }
        .metrics-grid {
            display: flex;
            gap: 8px;
        }
        .metric-card {
            flex: 1;
            background: #f8fafc;
            padding: 8px 6px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            text-align: center;
        }
        .metric-title {
            margin: 0 0 4px;
            font-size: 12px;
            color: #1e40af;
        }
        .metric-value {
            font-size: 16px;
            color: #3b82f6;
            font-weight: bold;
            margin: 0;
        }

        /* Corner logo on subsequent pages */
        .corner-logo {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 100px;
        }

        /* Other sections & tables */
        .section-title {
            font-size: 18px;
            color: #2563eb;
            margin: 30px 0 10px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
            font-size: 12px;
        }
        th {
            background: #f1f5f9;
            color: #1e40af;
            font-weight: 600;
            padding: 8px;
            border: 1px solid #e2e8f0;
            text-align: left;
        }
        td {
            padding: 6px 8px;
            border: 1px solid #e2e8f0;
            vertical-align: top;
        }
        .status-badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }
        .status-success {
            background: #dcfce7;
            color: #166534;
        }
        .status-failure {
            background: #fee2e2;
            color: #991b1b;
        }
    </style>
</head>
<body>
<!-- Cover Page -->
<div class="cover-page">
    {% if client_logo_base64 %}
    <div class="cover-logo">
        <img src="data:image/png;base64,{{ client_logo_base64 }}" style="max-width:200px; height:auto;" />
    </div>
    {% endif %}
    <h1 class="cover-title">SEO Rankings Analysis Report</h1>
    <p class="domain-line">{{ target_url }}</p>
    <p class="timestamp-line">Generated on {{ timestamp }}</p>

    <div class="summaries-row">
        <!-- Organic Summary -->
        <div class="summary-block">
            <div class="summary-title">Organic Search Rankings Summary</div>
            <div class="metrics-grid">
                <div class="metric-card">
                    <p class="metric-title">Total Queries</p>
                    <p class="metric-value">{{ total_queries }}</p>
                </div>
                <div class="metric-card">
                    <p class="metric-title">First Page</p>
                    <p class="metric-value">{{ ranked_queries }}</p>
                </div>
                <div class="metric-card">
                    <p class="metric-title">Rate</p>
                    <p class="metric-value">{{ ranking_rate }}%</p>
                </div>
            </div>
        </div>
        <!-- Local Summary -->
        <div class="summary-block">
            <div class="summary-title">Local Map Rankings Summary</div>
            <div class="metrics-grid">
                <div class="metric-card">
                    <p class="metric-title">Total Local</p>
                    <p class="metric-value">{{ total_local_listings }}</p>
                </div>
                <div class="metric-card">
                    <p class="metric-title">Top 3</p>
                    <p class="metric-value">{{ in_top_3_local }}</p>
                </div>
                <div class="metric-card">
                    <p class="metric-title">Rate</p>
                    <p class="metric-value">{{ local_rate }}%</p>
                </div>
            </div>
        </div>
    </div>
</div>

{% if client_logo_base64 %}
<img src="data:image/png;base64,{{ client_logo_base64 }}" class="corner-logo" />
{% endif %}

<!-- No <pdf:toc> tag here, so no automatic table of contents -->
<!-- Additional sections follow -->

<h2 class="section-title">Rankings Overview</h2>
{% for keyword_group in keywords|batch(5) %}
<table>
    <thead>
        <tr>
            <th>Location</th>
            {% for keyword in keyword_group %}
                <th>{{ keyword }}</th>
            {% endfor %}
        </tr>
    </thead>
    <tbody>
        {% for location in locations %}
        <tr>
            <td>{{ location }}</td>
            {% for keyword in keyword_group %}
            <td style="text-align: center;">
                {% set position = ranking_matrix.get((location, keyword), 'n/a') %}
                {% if position == 'n/a' %}
                    <span style="color: #94a3b8">-</span>
                {% elif position == 'Not on Page 1' %}
                    <span class="status-badge status-failure">{{ position }}</span>
                {% else %}
                    <span class="status-badge status-success">{{ position }}</span>
                {% endif %}
            </td>
            {% endfor %}
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endfor %}

<h2 class="section-title">Top Competitors by Keyword</h2>
{% for keyword in keywords %}
<table>
    <thead>
        <tr>
            <th colspan="3">{{ keyword }}</th>
        </tr>
        <tr>
            <th style="width: 80px;">Rank</th>
            <th>Domain</th>
            <th style="width: 120px;">Location</th>
        </tr>
    </thead>
    <tbody>
        {% for result in competitor_data.get(keyword, []) %}
        <tr>
            <td>#{{ result.rank }}</td>
            <td>{{ result.domain }}</td>
            <td>{{ result.location }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endfor %}

<h2 class="section-title">Local Business Results</h2>
{% for keyword in keywords %}
<table>
    <thead>
        <tr>
            <th colspan="5">{{ keyword }}</th>
        </tr>
        <tr>
            <th style="width: 80px;">Rank</th>
            <th>Business Name</th>
            <th style="width: 100px;">Rating</th>
            <th style="width: 100px;">Reviews</th>
            <th style="width: 120px;">Location</th>
        </tr>
    </thead>
    <tbody>
        {% for result in local_data.get(keyword, []) %}
        <tr>
            <td>#{{ loop.index }}</td>
            <td>{{ result.title }}</td>
            <td>
                {% if result.rating %}
                    ★ {{ "%.1f"|format(result.rating|float) }}
                {% else %}
                    -
                {% endif %}
            </td>
            <td>{{ result.reviews }}</td>
            <td>{{ result.location }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endfor %}
</body>
</html>
    """

    # Prepare data
    keywords = sorted(set(r['keyword'] for r in results))
    locations = sorted(set(r['location'] for r in results))

    ranking_matrix = {(r['location'], r['keyword']): r['target_position'] for r in results}

    competitor_data = {}
    for result in results:
        keyword = result['keyword']
        if keyword not in competitor_data:
            competitor_data[keyword] = []
        for rank, comp in enumerate(result['organic_results'], 1):
            competitor_data[keyword].append({
                'rank': rank,
                'domain': comp.get('domain', 'N/A'),
                'location': result['location']
            })

    local_data = {}
    for result in results:
        keyword = result['keyword']
        if keyword not in local_data:
            local_data[keyword] = []
        for local_result in result['local_results']:
            local_data[keyword].append({
                'title': local_result.get('title', 'N/A'),
                'rating': local_result.get('rating', None),
                'reviews': local_result.get('reviews', 0),
                'location': result['location']
            })

    total_queries = len(results)
    ranked_queries = len([r for r in results if '#' in r['target_position']])
    total_local_listings = sum(1 for r in results if r['local_results'])
    in_top_3_local = sum(
        1 for r in results if any(
            biz.get('title', '').lower() == target_url.lower()
            for biz in r['local_results'][:3]
        )
    )
    ranking_rate = (ranked_queries / total_queries * 100) if total_queries else 0
    local_rate = (in_top_3_local / total_local_listings * 100) if total_local_listings else 0

    template = jinja2.Template(template_string)
    html_report = template.render(
        timestamp=datetime.now(pytz.timezone('America/New_York')).strftime("%Y-%m-%d %I:%M:%S %p EST"),
        target_url=target_url,
        total_queries=total_queries,
        ranked_queries=ranked_queries,
        ranking_rate=f"{ranking_rate:.1f}",
        total_local_listings=total_local_listings,
        in_top_3_local=in_top_3_local,
        local_rate=f"{local_rate:.1f}",
        results=results,
        keywords=keywords,
        locations=locations,
        ranking_matrix=ranking_matrix,
        competitor_data=competitor_data,
        local_data=local_data,
        client_logo_base64=client_logo_base64
    )
    return html_report

# --- Main App Code (Keeps "By Chris Walnum" in the UI, but not in PDF) ------

def main():
    # Grab version from file
    script_path = os.path.basename(__file__)
    version = "Unknown"
    try:
        with open(script_path, 'r') as file:
            first_line = file.readline().strip()
            version = first_line.replace('# Version ', '')
    except:
        pass

    st.set_page_config(
        page_title="SEO Rankings Analyzer Pro - Test",
        page_icon="📊",
        layout="wide"
    )

    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
        st.session_state.start_time = None
        st.session_state.results = []

    # Minimal custom CSS for app layout
    st.markdown("""
        <style>
            .stApp {
                max-width: 1200px;
                margin: 0 auto;
            }
            .stButton>button {
                width: 100%;
            }
        </style>
    """, unsafe_allow_html=True)

    # App Title + "By Chris Walnum" in the UI only
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.markdown("""
            <div style="display: flex; align-items: center; margin-bottom: 20px;">
                <div style="color: #FF4B4B; font-size: 2.5em; margin-right: 10px;">🎯</div>
                <div style="color: #262730; font-size: 1.8em; font-weight: 600;">
                    SEO Rankings Analyzer Pro
                </div>
            </div>
        """, unsafe_allow_html=True)
        # "By Chris Walnum" here is purely in the UI
        st.markdown(
            '<p style="color: #777; font-size: 14px; margin-top: -10px;">By Chris Walnum</p>',
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f'<p style="color: #666; font-size: 14px; margin-top: 15px; text-align: right;">v{version}</p>',
            unsafe_allow_html=True
        )

    st.markdown("""
        <div style="background-color: #f8f9fa; padding: 1em; border-radius: 0.5em; margin: 1em 0;">
            Analyze a website's search rankings across multiple locations with detailed insights.
        </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("Analysis Configuration")
        target_url = st.text_input("Target Website URL", placeholder="example.com")
        if target_url:
            target_url = (
                target_url
                .replace('http://', '')
                .replace('https://', '')
                .replace('www.', '')
                .rstrip('/')
            )

        st.markdown("### Keywords")
        keywords = st.text_area("", placeholder="One keyword per line")

        st.markdown("### Locations")
        locations = st.text_area("", placeholder="City, State or 5-digit ZIP")

        st.markdown("### Client Logo (optional)")
        client_logo_file = st.file_uploader("Upload PNG/JPG", type=["png", "jpg", "jpeg"])

        analyze_button = st.button("🚀 Run Analysis")

    if analyze_button:
        if not all([target_url, keywords, locations]):
            st.error("Please fill in the URL, keywords, and locations.")
            return

        if "VALUESERP_API_KEY" not in st.secrets:
            st.error("No ValueSERP API key found in secrets. Please configure it.")
            return

        st.session_state.start_time = time.time()

        keyword_list = [k.strip() for k in keywords.split('\n') if k.strip()]
        location_list = [l.strip() for l in locations.split('\n') if l.strip()]

        processed_locations = []
        invalid_locs = []
        for loc in location_list:
            if loc.isdigit():
                if len(loc) == 5:
                    processed_locations.append(loc)
                else:
                    invalid_locs.append(f"• {loc} (invalid ZIP code length)")
            else:
                parts = [p.strip() for p in loc.split(',')]
                if len(parts) == 2:
                    processed_locations.append({'city': parts[0], 'state': parts[1]})
                else:
                    invalid_locs.append(f"• {loc} (invalid format - use 'City, State' or 5-digit ZIP)")

        if invalid_locs:
            st.error("Invalid location format:\n" + "\n".join(invalid_locs))
            return

        # Validate
        with st.expander("📍 Location Validation Progress", expanded=True):
            progress_text = st.empty()
            progress_bar = st.progress(0)
            valid_locations = []
            skipped_locations = []

            def validate_location_batch(locs):
                return [loc for loc in locs if validate_location(loc)]

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=3) as executor:
                chunk_size = max(1, len(processed_locations) // 3)
                location_chunks = [
                    processed_locations[i:i+chunk_size]
                    for i in range(0, len(processed_locations), chunk_size)
                ]
                futures = {
                    executor.submit(validate_location_batch, chunk): i
                    for i, chunk in enumerate(location_chunks)
                }
                done_chunks = 0
                for fut in as_completed(futures):
                    batch_result = fut.result()
                    idx = futures[fut]
                    chunk = location_chunks[idx]

                    for loc in chunk:
                        if loc not in batch_result:
                            if isinstance(loc, dict):
                                loc_str = f"{loc['city']}, {loc['state']}"
                                skipped_locations.append(loc_str)
                            else:
                                skipped_locations.append(loc)
                        else:
                            valid_locations.append(loc)

                    done_chunks += 1
                    progress_bar.progress(done_chunks / len(location_chunks))
                    progress_text.text(f"Validated {done_chunks}/{len(location_chunks)} chunks...")

            if skipped_locations:
                st.warning("Skipped:\n" + "\n".join(skipped_locations))

            if not valid_locations:
                st.error("No valid locations remain.")
                return

        # Build queries
        search_queries = []
        for loc in valid_locations:
            if isinstance(loc, str):
                location_str = loc
            else:
                location_str = f"{loc['city']}, {loc['state']}"
            for kw in keyword_list:
                search_queries.append({
                    'keyword': kw,
                    'location': location_str,
                    'query': f"{kw} {location_str}"
                })

        # Parallel SERP calls
        with st.expander("🔍 Rankings Analysis Progress", expanded=True):
            progress_text = st.empty()
            progress_bar = st.progress(0)
            results = parallel_process_queries(
                search_queries,
                target_url,
                progress_text,
                progress_bar,
                st.secrets["VALUESERP_API_KEY"]
            )

        st.session_state.results = results
        st.session_state.analysis_complete = True
        st.session_state.analysis_duration = round(time.time() - st.session_state.start_time, 1)
        st.info(f"✨ Analysis completed in {st.session_state.analysis_duration} seconds.")

    # Display
    if st.session_state.analysis_complete and st.session_state.results:
        results = st.session_state.results
        df_overview = pd.DataFrame(results)

        st.markdown("### 📊 Analysis Summary")
        total_queries = len(results)
        ranked_queries = len([r for r in results if '#' in r['target_position']])
        total_local_listings = sum(1 for r in results if r['local_results'])
        in_top_3_local = sum(
            1 for r in results if any(
                b.get('title', '').lower() == target_url.lower()
                for b in r['local_results'][:3]
            )
        )
        local_rate = (in_top_3_local / total_local_listings * 100) if total_local_listings else 0

        colA, colB, colC = st.columns(3)
        with colA:
            st.metric("Total Queries", total_queries)
        with colB:
            st.metric("First Page Rankings", ranked_queries)
        with colC:
            st.metric("Ranking Rate", f"{(ranked_queries/total_queries*100):.1f}%")

        st.markdown("### 📍 Local Rankings Summary")
        colD, colE, colF = st.columns(3)
        with colD:
            st.metric("Total Local Listings", total_local_listings)
        with colE:
            st.metric("Top 3", in_top_3_local)
        with colF:
            st.metric("Local Rate", f"{local_rate:.1f}%")

        # Pivot table
        st.markdown("### 📈 Rankings Overview")
        pivot_data = pd.pivot_table(
            df_overview,
            index='location',
            columns='keyword',
            values='target_position',
            aggfunc=lambda x: max(
                x,
                key=lambda y: float('inf') if y == 'Not on Page 1' else float(y.replace('#', ''))
            )
        )

        def style_ranking(val):
            if '#' in str(val):
                return 'background-color: #dcfce7; color: #166534'
            elif val == 'Not on Page 1':
                return 'background-color: #fee2e2; color: #991b1b'
            else:
                return ''

        styled_pivot = pivot_data.style.applymap(style_ranking)
        st.dataframe(styled_pivot, height=400)

        tab1, tab2 = st.tabs(["🔍 Organic Results", "📍 Local Results"])
        with tab1:
            for result in results:
                label = f"{result['keyword']} in {result['location']}"
                with st.expander(label):
                    for i, org in enumerate(result['organic_results'], 1):
                        st.markdown(f"**#{i}** - {org.get('title', 'N/A')}")
                        st.markdown(f"Domain: {org.get('domain', 'N/A')}")
                        st.markdown("---")
        with tab2:
            for result in results:
                label = f"{result['keyword']} in {result['location']}"
                with st.expander(label):
                    for i, loc in enumerate(result['local_results'], 1):
                        st.markdown(f"**#{i}** - {loc.get('title', 'N/A')}")
                        rating = loc.get('rating')
                        if rating:
                            st.markdown(f"Rating: {rating}★ | Reviews: {loc.get('reviews', 0)}")
                        else:
                            st.markdown(f"Rating: N/A | Reviews: {loc.get('reviews', 0)}")
                        st.markdown("---")

        # Client logo
        client_logo_b64 = None
        if client_logo_file:
            client_logo_b64 = base64.b64encode(client_logo_file.read()).decode()

        # Generate final PDF/HTML
        html_report = generate_html_report(results, target_url, client_logo_b64)

        st.subheader("📥 Export Options")
        c1, c2, c3 = st.columns(3)
        base_filename = f"{target_url.replace('/','').replace(':','').replace('.','_')}_SEO_Analysis_Report_{datetime.now().strftime('%Y%m%d')}"

        with c1:
            st.download_button(
                label="📄 Download HTML Report",
                data=html_report,
                file_name=f"{base_filename}.html",
                mime="text/html"
            )
        with c2:
            csv_data = df_overview.to_csv(index=False)
            st.download_button(
                label="📊 Download CSV",
                data=csv_data,
                file_name=f"{base_filename}.csv",
                mime="text/csv"
            )
        with c3:
            pdf_bytes = io.BytesIO()
            pisa.CreatePDF(io.StringIO(html_report), dest=pdf_bytes)
            pdf_bytes.seek(0)
            st.download_button(
                label="📑 Download PDF Report",
                data=pdf_bytes,
                file_name=f"{base_filename}.pdf",
                mime="application/pdf"
            )

if __name__ == "__main__":
    main()
