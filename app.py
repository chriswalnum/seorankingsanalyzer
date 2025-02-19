# Version 1.5.1
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

# Page config
st.set_page_config(
    page_title="SEO Rankings Analyzer Pro - Test",
    page_icon="📊",
    layout="wide"
)

# Initialize session state
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
    st.session_state.start_time = None

# Enhanced Custom CSS
st.markdown("""
    <style>
        .stApp {
            max-width: 1200px;
            margin: 0 auto;
        }
        .metric-card {
            background-color: #f8fafc;
            padding: 1.5rem;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin: 1rem 0;
        }
        .results-table {
            font-size: 14px;
        }
        .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 500;
        }
        .status-success {
            background-color: #dcfce7;
            color: #166534;
        }
        .status-failure {
            background-color: #fee2e2;
            color: #991b1b;
        }
        .stButton>button {
            width: 100%;
        }
        .info-box {
            padding: 1rem;
            background-color: #f1f5f9;
            border-radius: 6px;
            margin: 1rem 0;
        }
        .stProgress > div > div > div {
            background-color: #3b82f6;
        }
    </style>
""", unsafe_allow_html=True)

# Create a global rate limiter instance
geocoding_limiter = ThreadSafeRateLimiter(calls_per_second=1)

def validate_location(location):
    """Validate if a location exists using GeoPy"""
    debug_prefix = "[Location Validation]"
    print(f"{debug_prefix} Starting validation for input: {location}")
    geolocator = Nominatim(user_agent="seo_analysis_tool")
    try:
        print(f"{debug_prefix} Input type: {type(location)}")
        if isinstance(location, str) and location.isdigit() and len(location) == 5:
            search_term = f"{location}, USA"
            print(f"{debug_prefix} Processing as ZIP code")
        else:
            search_term = f"{location['city']}, {location['state']}, USA"
            print(f"{debug_prefix} Processing as City/State pair")
            
        print(f"{debug_prefix} Search term: {search_term}")
        print(f"{debug_prefix} Attempting geocoding...")
        geocoding_limiter.wait()
        location_data = geolocator.geocode(search_term)
        if location_data:
            print(f"{debug_prefix} Success! Found: {location_data.address}")
            return True
        else:
            print(f"{debug_prefix} Location not found in database")
            return False
    except KeyError as ke:
        print(f"{debug_prefix} Error: Invalid dictionary format - {ke}")
        return False
    except Exception as e:
        print(f"{debug_prefix} Error: {str(e)}")
        return False

@sleep_and_retry
@limits(calls=5, period=1)
def rate_limited_api_call(base_url, params):
    """Make a rate-limited API call"""
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    return response.json()

def fetch_serp_data(query):
    """Fetch SERP data from ValueSERP API with rate limiting"""
    base_url = "https://api.valueserp.com/search"
    params = {
        'api_key': st.secrets["VALUESERP_API_KEY"],
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

def process_query(query, target_url):
    """Process a single SERP query and return results"""
    serp_data = fetch_serp_data(query)
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

def parallel_process_queries(search_queries, target_url, progress_text, progress_bar):
    """Process queries in parallel with progress tracking"""
    results = []
    completed = 0
    total = len(search_queries)
    progress_lock = threading.Lock()
    
    def update_progress():
        nonlocal completed
        with progress_lock:
            completed += 1
            progress = completed / total
            progress_bar.progress(progress)
            progress_text.text(f"Processed {completed}/{total} queries...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_query = {
            executor.submit(process_query, query, target_url): query 
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

def generate_html_report(results, target_url, logo_html=""):
    template_string = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>SEO Analysis Report</title>
        <style>
            @page {
                margin: 2.5cm;
            }
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #1a1a1a;
                margin: 0;
                padding: 0;
            }
            .header {
                text-align: center;
                margin-bottom: 3rem;
                border-bottom: 2px solid #2563eb;
                padding-bottom: 1rem;
            }
            .logo-container {
                margin-bottom: 10px;
                text-align: center;
            }
            .logo-container img {
                max-height: 80px;
            }
            .header h1 {
                color: #2563eb;
                font-size: 28px;
                margin-bottom: 0.5rem;
            }
            .metrics {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1.5rem;
                margin: 2rem 0;
            }
            .metric-card {
                background: #f8fafc;
                padding: 1.5rem;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
                text-align: center;
            }
            .section-title {
                color: #2563eb;
                font-size: 24px;
                margin: 2.5rem 0 1.5rem;
                border-bottom: 2px solid #e2e8f0;
                padding-bottom: 0.5rem;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 1.5rem 0;
            }
            th {
                background: #f1f5f9;
                color: #1e40af;
                font-weight: 600;
                text-align: left;
            }
            th, td {
                padding: 12px;
                border: 1px solid #e2e8f0;
            }
            .status-badge {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 14px;
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
        <div class="header">
            <div class="logo-container">
                {{ logo_html|safe }}
            </div>
            <h1>SEO Rankings Analysis Report</h1>
            <p>{{ target_url }}</p>
            <p>Generated on {{ timestamp }}</p>
        </div>

        <div class="section-title">Organic Search Rankings Summary</div>
        <div class="metrics">
            <div class="metric-card">
                <h3>Total Queries</h3>
                <div class="metric-value">{{ total_queries }}</div>
            </div>
            <div class="metric-card">
                <h3>First Page Rankings</h3>
                <div class="metric-value">{{ ranked_queries }}</div>
            </div>
            <div class="metric-card">
                <h3>Ranking Rate</h3>
                <div class="metric-value">{{ ranking_rate }}%</div>
            </div>
        </div>

        <div class="section-title">Local Map Rankings Summary</div>
        <div class="metrics">
            <div class="metric-card">
                <h3>Total Local Listings</h3>
                <div class="metric-value">{{ total_local_listings }}</div>
            </div>
            <div class="metric-card">
                <h3>In Top 3 Listings</h3>
                <div class="metric-value">{{ in_top_3_local }}</div>
            </div>
            <div class="metric-card">
                <h3>Top 3 Rate</h3>
                <div class="metric-value">{{ local_rate }}%</div>
            </div>
        </div>

        <div class="section-title">Rankings Overview</div>
        {% for keyword_group in keywords|batch(5) %}
        <div class="keyword-table">
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
                        <td style="text-align: center">
                            {% set position = ranking_matrix.get((location, keyword), 'n/a') %}
                            {% if position == 'n/a' %}
                            <span style="color: #94a3b8">-</span>
                            {% elif position == 'Not on Page 1' %}
                            <span style="background-color: #fee2e2; color: #991b1b; padding: 2px 6px; border-radius: 4px;">{{ position }}</span>
                            {% else %}
                            <span style="background-color: #dcfce7; color: #166534; padding: 2px 6px; border-radius: 4px;">{{ position }}</span>
                            {% endif %}
                        </td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endfor %}

        <div class="section-title">Top Competitors by Keyword</div>
        {% for keyword in keywords %}
        <table class="competitors-table">
            <thead>
                <tr>
                    <th colspan="3">{{ keyword }}</th>
                </tr>
                <tr>
                    <th style="width: 80px">Rank</th>
                    <th>Domain</th>
                    <th style="width: 120px">Location</th>
                </tr>
            </thead>
            <tbody>
                {% for result in competitor_data.get(keyword, []) %}
                <tr>
                    <td class="competitor-rank">#{{ result.rank }}</td>
                    <td>{{ result.domain }}</td>
                    <td>{{ result.location }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endfor %}

        <div class="section-title">Local Business Results</div>
        {% for keyword in keywords %}
        <table class="competitors-table">
            <thead>
                <tr>
                    <th colspan="5">{{ keyword }}</th>
                </tr>
                <tr>
                    <th style="width: 80px">Rank</th>
                    <th>Business Name</th>
                    <th style="width: 100px">Rating</th>
                    <th style="width: 100px">Reviews</th>
                    <th style="width: 120px">Location</th>
                </tr>
            </thead>
            <tbody>
                {% for result in local_data.get(keyword, []) %}
                <tr>
                    <td class="competitor-rank">#{{ loop.index }}</td>
                    <td>{{ result.title }}</td>
                    <td style="text-align: center">{% if result.rating %}★ {{ "%.1f"|format(result.rating|float) }}{% endif %}</td>
                    <td style="text-align: center">{{ result.reviews }}</td>
                    <td class="location-cell">{{ result.location }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endfor %}
    </body>
    </html>
    """
    
    keywords = sorted(set(r['keyword'] for r in results))
    locations = sorted(set(r['location'] for r in results))
    ranking_matrix = {(r['location'], r['keyword']): r['target_position'] for r in results}
    
    competitor_data = {}
    for result in results:
        keyword = result['keyword']
        if keyword not in competitor_data:
            competitor_data[keyword] = []
        competitors = result['organic_results'][:3]
        for rank, comp in enumerate(competitors, 1):
            competitor_data[keyword].append({
                'rank': rank,
                'domain': comp.get('domain', 'N/A'),
                'location': result['location']
            })
    
    local_data = {}
    for result in results:
        keyword = result['keyword']
        location = result['location']
        if keyword not in local_data:
            local_data[keyword] = []
        for local_result in result['local_results']:
            local_data[keyword].append({
                'title': local_result.get('title', 'N/A'),
                'rating': local_result.get('rating', None),
                'reviews': local_result.get('reviews', 0),
                'location': location
            })
    
    template = jinja2.Template(template_string)
    total_queries = len(results)
    ranked_queries = len([r for r in results if '#' in r['target_position']])
    ranking_rate = f"{(ranked_queries/total_queries*100):.1f}"
    total_local_listings = sum(1 for r in results if r['local_results'])
    in_top_3_local = sum(1 for r in results if any(
        business.get('title', '').lower() == target_url.lower() 
        for business in r['local_results'][:3]
    ))
    local_rate = f"{(in_top_3_local / total_local_listings * 100):.1f}" if total_local_listings > 0 else "0.0"
    
    html_report = template.render(
        timestamp=datetime.now(pytz.timezone('America/New_York')).strftime("%Y-%m-%d %I:%M:%S %p EST"),
        target_url=target_url,
        total_queries=total_queries,
        ranked_queries=ranked_queries,
        ranking_rate=ranking_rate,
        results=results,
        keywords=keywords,
        locations=locations,
        ranking_matrix=ranking_matrix,
        competitor_data=competitor_data,
        local_data=local_data,
        total_local_listings=total_local_listings,
        in_top_3_local=in_top_3_local,
        local_rate=local_rate,
        logo_html=logo_html
    )
    
    return html_report

def main():
    # Get version number from first line comment
    with open(__file__, 'r') as file:
        first_line = file.readline().strip()
        version = first_line.replace('# Version ', '')

    # Sidebar: Analysis configuration & logo upload
    with st.sidebar:
        st.header("Analysis Configuration")
        target_url = st.text_input(
            "Target Website URL",
            placeholder="example.com",
            help="Enter your website's domain without http:// or www"
        )
        if target_url:
            target_url = target_url.replace('http://', '').replace('https://', '').replace('www.', '').rstrip('/')
        st.markdown("### Keywords")
        st.markdown("Enter one keyword per line")
        keywords = st.text_area("", placeholder="Enter your keywords here", key="keywords")
        st.markdown("### Locations")
        st.markdown("""Enter one location per line:
- City, State (e.g., New York, NY)
- ZIP code (e.g., 90210)""")
        locations = st.text_area("", placeholder="Enter your locations here", key="locations")
        
        # New: Logo Upload Option
        logo_file = st.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"])
        if logo_file is not None:
            logo_bytes = logo_file.read()
            logo_base64 = base64.b64encode(logo_bytes).decode('utf-8')
            logo_mime = logo_file.type
            logo_img_html = f'<img src="data:{logo_mime};base64,{logo_base64}" alt="Logo">'
        else:
            logo_img_html = '<div style="color: #FF4B4B; font-size: 2.5em; margin-right: 10px;">🎯</div>'
        
        analyze_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    # Header with logo and version
    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.markdown(f"""
            <div style="display: flex; align-items: center; margin-bottom: 20px;">
                {logo_img_html}
                <div style="color: #262730; font-size: 1.8em; font-weight: 600;">
                    SEO Rankings Analyzer Pro
                </div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f'<p style="color: #666; font-size: 14px; margin-top: 15px; text-align: right;">v{version}</p>', unsafe_allow_html=True)
    st.markdown("""
        <div style="background-color: #f8f9fa; padding: 1em; border-radius: 0.5em; margin: 1em 0;">
            Analyze a website's search rankings across multiple locations with detailed insights.
        </div>
    """, unsafe_allow_html=True)

    if analyze_button:
        if not all([target_url, keywords, locations]):
            st.error("Please fill in all required fields before running the analysis.")
            return
        
        st.session_state.start_time = time.time()
        
        with st.spinner("🔍 Analyzing search rankings..."):
            keyword_list = [k.strip() for k in keywords.split('\n') if k.strip()]
            location_list = [l.strip() for l in locations.split('\n') if l.strip()]
            processed_locations = []
            invalid_locations = []
            for loc in location_list:
                loc = loc.strip()
                if not loc:
                    continue
                if loc.isdigit():
                    if len(loc) == 5:
                        processed_locations.append(loc)
                    else:
                        invalid_locations.append(f"• {loc} (invalid ZIP code - must be 5 digits)")
                else:
                    parts = [p.strip() for p in loc.split(',')]
                    if len(parts) == 2:
                        processed_locations.append({
                            'city': parts[0],
                            'state': parts[1].strip()
                        })
                    else:
                        invalid_locations.append(f"• {loc} (invalid format - use 'City, State' or 5-digit ZIP)")
            if invalid_locations:
                error_message = """Invalid location formats detected:

{}

Please use either:
- City, State (e.g., New York, NY)
- ZIP code (e.g., 90210)

Please correct all location formats before running the analysis."""
                invalid_list = "\n".join(invalid_locations)
                st.error(error_message.format(invalid_list))
                return

            with st.expander("📍 Location Validation Progress", expanded=True):
                progress_text = st.empty()
                progress_bar = st.progress(0)
                valid_locations = []
                def validate_location_batch(locations):
                    return [loc for loc in locations if validate_location(loc)]
                skipped_locations = []
                with ThreadPoolExecutor(max_workers=3) as executor:
                    chunk_size = max(1, len(processed_locations) // 3)
                    location_chunks = [processed_locations[i:i + chunk_size] 
                                    for i in range(0, len(processed_locations), chunk_size)]
                    future_to_chunk = {executor.submit(validate_location_batch, chunk): i 
                                     for i, chunk in enumerate(location_chunks)}
                    completed_chunks = 0
                    for future in as_completed(future_to_chunk):
                        chunk_valid_locations = future.result()
                        chunk_index = future_to_chunk[future]
                        chunk = location_chunks[chunk_index]
                        for loc in chunk:
                            if isinstance(loc, str):
                                if loc not in [str(x) if isinstance(x, str) else None for x in chunk_valid_locations]:
                                    skipped_locations.append(loc)
                            else:
                                loc_str = f"{loc['city']}, {loc['state']}"
                                if loc not in chunk_valid_locations:
                                    skipped_locations.append(loc_str)
                        valid_locations.extend(chunk_valid_locations)
                        completed_chunks += 1
                        progress_bar.progress(completed_chunks / len(location_chunks))
                        progress_text.text(f"Validated {completed_chunks}/{len(location_chunks)} location groups...")
                if skipped_locations:
                    warning_locations = "\n• ".join(skipped_locations)
                    st.warning(f"""The following locations could not be validated and will be skipped:
- {warning_locations}

Please check for typos or verify these locations exist.""")
                if not valid_locations:
                    st.error("No valid locations found. Please check your inputs and try again.")
                    return

            search_queries = []
            for location in valid_locations:
                if isinstance(location, str):
                    location_string = location
                else:
                    location_string = f"{location['city']}, {location['state']}"
                for keyword in keyword_list:
                    search_queries.append({
                        'keyword': keyword,
                        'location': location_string,
                        'query': f"{keyword} {location_string}"
                    })

            with st.expander("🔍 Rankings Analysis Progress", expanded=True):
                progress_text = st.empty()
                progress_bar = st.progress(0)
                results = parallel_process_queries(search_queries, target_url, progress_text, progress_bar)

            analysis_duration = round(time.time() - st.session_state.start_time, 1)
            st.session_state.results = results
            st.session_state.analysis_complete = True
            st.session_state.analysis_duration = analysis_duration
            st.info(f"✨ Analysis completed in {analysis_duration} seconds")

    if st.session_state.analysis_complete and hasattr(st.session_state, 'results'):
        results = st.session_state.results
        st.markdown("### 📊 Analysis Summary")
        col1, col2, col3 = st.columns(3)
        total_queries = len(results)
        ranked_queries = len([r for r in results if '#' in r['target_position']])
        total_local_listings = len([r for r in results if r['local_results']])
        in_top_3_local = len([r for r in results if any(
            business.get('title', '').lower() == target_url.lower() 
            for business in r.get('local_results', [])[:3]
        )])
        local_rate = f"{(in_top_3_local / total_local_listings * 100):.1f}" if total_local_listings > 0 else "0.0"

        with col1:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>Total Queries</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {total_queries}
                    </div>
                </div>""",
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>First Page Rankings</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {ranked_queries}
                    </div>
                </div>""",
                unsafe_allow_html=True
            )
        with col3:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>Ranking Rate</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {(ranked_queries/total_queries*100):.1f}%
                    </div>
                </div>""",
                unsafe_allow_html=True
            )
        
        st.markdown("### 📍 Local Rankings Summary")
        col4, col5, col6 = st.columns(3)
        with col4:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>Total Local Listings</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {total_local_listings}
                    </div>
                </div>""",
                unsafe_allow_html=True
            )
        with col5:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>In Top 3 Listings</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {in_top_3_local}
                    </div>
                </div>""",
                unsafe_allow_html=True
            )
        with col6:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>Top 3 Rate</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {local_rate}%
                    </div>
                </div>""",
                unsafe_allow_html=True
            )

        st.markdown("### 📈 Rankings Overview")
        df_overview = pd.DataFrame(results)
        pivot_data = pd.pivot_table(
            df_overview,
            index='location',
            columns='keyword',
            values='target_position',
            aggfunc=lambda x: max(x, key=lambda y: float('inf') if y == 'Not on Page 1' else float(y.replace('#', '')))
        )
        def style_ranking(val):
            if '#' in str(val):
                return 'background-color: #dcfce7; color: #166534'
            return 'background-color: #fee2e2; color: #991b1b'
        styled_pivot = pivot_data.style.applymap(style_ranking)
        st.dataframe(styled_pivot, height=400)

        tab1, tab2 = st.tabs(["🔍 Organic Results", "📍 Local Results"])
        with tab1:
            for result in results:
                with st.expander(f"{result['keyword']} in {result['location']}"):
                    for idx, org in enumerate(result['organic_results'], 1):
                        st.markdown(f"**#{idx}** - {org.get('title', 'N/A')}")
                        st.markdown(f"Domain: {org.get('domain', 'N/A')}")
                        st.markdown("---")
        with tab2:
            for result in results:
                with st.expander(f"{result['keyword']} in {result['location']}"):
                    for idx, loc in enumerate(result['local_results'], 1):
                        st.markdown(f"**#{idx}** - {loc.get('title', 'N/A')}")
                        st.markdown(f"Rating: {loc.get('rating', 'N/A')}★ ({loc.get('reviews', '0')} reviews)")
                        st.markdown("---")

        html_report = generate_html_report(results, target_url, logo_html=logo_img_html)
        st.subheader("📥 Export Options")
        col1, col2, col3 = st.columns(3)
        clean_domain = target_url.replace('/', '').replace(':', '').replace('.', '_')
        timestamp = datetime.now().strftime("%Y%m%d")
        base_filename = f"{clean_domain}_SEO_Analysis_Report_{timestamp}"
        with col1:
            st.download_button(
                label="📄 Download HTML Report",
                data=html_report,
                file_name=f"{base_filename}.html",
                mime="text/html"
            )
        with col2:
            csv = df_overview.to_csv(index=False)
            st.download_button(
                label="📊 Download CSV",
                data=csv,
                file_name=f"{base_filename}.csv",
                mime="text/csv"
            )
        with col3:
            pdf_bytes = io.BytesIO()
            pisa.CreatePDF(html_report, dest=pdf_bytes)
            pdf_bytes.seek(0)
            st.download_button(
                label="📑 Download PDF Report",
                data=pdf_bytes,
                file_name=f"{base_filename}.pdf",
                mime="application/pdf"
            )
        
if __name__ == "__main__":
    main()
