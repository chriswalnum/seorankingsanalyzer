# Version 1.5.2
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
        else:  # city_state dict
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
    """
    Generates a PDF/HTML with:
    - Minimal Table of Contents
    - Combined 'Top Competitors' table
    - Combined 'Local Business Results' table
    - Page numbers in the footer
    """
    # Flatten competitor_data and local_data for single tables
    competitor_data_flat = []
    local_data_flat = []
    
    # Build competitor_data from the existing approach
    # - We'll store for each (keyword -> top 3 organic) the competitor domain, rank, location
    competitor_dict = {}
    # Similarly for local_data
    local_dict = {}
    
    # 1) Identify all keywords & locations
    keywords = sorted(set(r['keyword'] for r in results))
    locations = sorted(set(r['location'] for r in results))
    
    # 2) Build a ranking matrix (same as before) for the 'Rankings Overview' table
    ranking_matrix = {(r['location'], r['keyword']): r['target_position'] for r in results}
    
    # 3) Extract competitor data from each result
    for r in results:
        keyword = r['keyword']
        location = r['location']
        if 'organic_results' in r:
            for rank_idx, comp in enumerate(r['organic_results'], start=1):
                competitor_data_flat.append({
                    'keyword': keyword,
                    'rank': rank_idx,
                    'domain': comp.get('domain', 'N/A'),
                    'location': location
                })
        if 'local_results' in r:
            for rank_idx, loc_res in enumerate(r['local_results'], start=1):
                local_data_flat.append({
                    'keyword': keyword,
                    'rank': rank_idx,
                    'title': loc_res.get('title', 'N/A'),
                    'rating': loc_res.get('rating', None),
                    'reviews': loc_res.get('reviews', 0),
                    'location': location
                })
    
    # Summaries
    total_queries = len(results)
    ranked_queries = len([r for r in results if '#' in r['target_position']])
    ranking_rate = f"{(ranked_queries/total_queries*100):.1f}"
    total_local_listings = len([r for r in results if r['local_results']])
    in_top_3_local = len([r for r in results if any(
        business.get('title', '').lower() == target_url.lower() 
        for business in r['local_results'][:3]
    )])
    local_rate = f"{(in_top_3_local / total_local_listings * 100):.1f}" if total_local_listings > 0 else "0.0"
    
    # Current timestamp
    now_est = datetime.now(pytz.timezone('America/New_York'))
    timestamp_str = now_est.strftime("%Y-%m-%d %I:%M:%S %p EST")
    
    # HTML template with:
    # - Minimal Table of Contents
    # - Combined competitor table
    # - Combined local results table
    # - Page number CSS in the @page rule
    template_string = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>SEO Analysis Report</title>
    <style>
        /* Page margin & page numbering */
        @page {
            margin: 2.5cm;
            @bottom-center {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 12px;
                color: #666;
            }
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
            margin-bottom: 1rem;
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
        .table-of-contents {
            margin: 1rem 2rem;
        }
        .table-of-contents h2 {
            font-size: 20px;
            color: #2563eb;
            margin-bottom: 0.5rem;
        }
        .table-of-contents ol {
            margin-left: 1.2rem;
        }
        .section-title {
            color: #2563eb;
            font-size: 22px;
            margin: 2rem 0 1rem;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.5rem;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem;
            margin: 1.5rem 0;
        }
        .metric-card {
            background: #f8fafc;
            padding: 1.5rem;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            text-align: center;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            font-size: 0.9rem; /* Slightly smaller font to save space */
        }
        th {
            background: #f1f5f9;
            color: #1e40af;
            font-weight: 600;
            text-align: left;
            padding: 8px;
        }
        td {
            padding: 8px;
            border: 1px solid #e2e8f0;
        }
        .keyword-col {
            width: 180px;
        }
        .rank-col {
            width: 60px;
            text-align: center;
        }
        .location-col {
            width: 140px;
        }
        .section-break {
            page-break-before: always;
        }
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <div class="logo-container">
            {{ logo_html|safe }}
        </div>
        <h1>SEO Rankings Analysis Report</h1>
        <p>{{ target_url }}</p>
        <p>Generated on {{ timestamp }}</p>
    </div>

    <!-- Table of Contents -->
    <div class="table-of-contents">
        <h2>Table of Contents</h2>
        <ol>
            <li>Organic Search Rankings Summary</li>
            <li>Local Map Rankings Summary</li>
            <li>Rankings Overview</li>
            <li>Top Competitors</li>
            <li>Local Business Results</li>
        </ol>
    </div>

    <!-- Organic Search Rankings Summary -->
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
            <div class="metric-value">{{ ranking_rate }}%</</div>
        </div>
    </div>

    <!-- Local Map Rankings Summary -->
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

    <!-- Rankings Overview -->
    <div class="section-title">Rankings Overview</div>
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
    {% endfor %}

    <!-- Combined Top Competitors Section -->
    <div class="section-break"></div>
    <div class="section-title">Top Competitors</div>
    <table>
        <thead>
            <tr>
                <th class="keyword-col">Keyword</th>
                <th class="rank-col">Rank</th>
                <th>Domain</th>
                <th class="location-col">Location</th>
            </tr>
        </thead>
        <tbody>
            {% for row in competitor_data_flat %}
            <tr>
                <td>{{ row.keyword }}</td>
                <td>#{{ row.rank }}</td>
                <td>{{ row.domain }}</td>
                <td>{{ row.location }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <!-- Combined Local Business Results Section -->
    <div class="section-title">Local Business Results</div>
    <table>
        <thead>
            <tr>
                <th class="keyword-col">Keyword</th>
                <th class="rank-col">Rank</th>
                <th>Business Name</th>
                <th style="width: 80px; text-align:center;">Rating</th>
                <th style="width: 80px; text-align:center;">Reviews</th>
                <th class="location-col">Location</th>
            </tr>
        </thead>
        <tbody>
            {% for row in local_data_flat %}
            <tr>
                <td>{{ row.keyword }}</td>
                <td>#{{ row.rank }}</td>
                <td>{{ row.title }}</td>
                <td style="text-align: center">
                    {% if row.rating %}★ {{ "%.1f"|format(row.rating|float) }}{% endif %}
                </td>
                <td style="text-align: center">{{ row.reviews }}</td>
                <td>{{ row.location }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
""".strip()

    template = jinja2.Template(template_string)
    html_report = template.render(
        timestamp=timestamp_str,
        target_url=target_url,
        total_queries=total_queries,
        ranked_queries=ranked_queries,
        ranking_rate=ranking_rate,
        results=results,
        keywords=keywords,
        locations=locations,
        ranking_matrix=ranking_matrix,
        competitor_data_flat=competitor_data_flat,
        local_data_flat=local_data_flat,
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

    # Header (with "By Chris Walnum" subheading) - same as v1.5.1
    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.markdown("""
            <div style="display: flex; align-items: center; margin-bottom: 20px;">
                <div style="color: #FF4B4B; font-size: 2.5em; margin-right: 10px;">🎯</div>
                <div>
                    <div style="color: #262730; font-size: 1.8em; font-weight: 600;">
                        SEO Rankings Analyzer Pro
                    </div>
                    <div style="color: #888888; font-size: 0.9em; margin-top: 5px;">
                        By Chris Walnum
                    </div>
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

    # Sidebar for inputs
    with st.sidebar:
        st.header("Analysis Configuration")
        
        # Target URL input
        target_url = st.text_input(
            "Target Website URL",
            placeholder="example.com",
            help="Enter your website's domain without http:// or www"
        )
        if target_url:
            target_url = target_url.replace('http://', '').replace('https://', '').replace('www.', '').rstrip('/')

        # Keywords input
        st.markdown("### Keywords")
        st.markdown("Enter one keyword per line")
        keywords = st.text_area("", placeholder="Enter your keywords here", key="keywords")
        
        # Locations input
        st.markdown("### Locations")
        st.markdown("""Enter one location per line:
- City, State (e.g., New York, NY)
- ZIP code (e.g., 90210)""")
        locations = st.text_area("", placeholder="Enter your locations here", key="locations")

        # Logo upload for PDF only (not displayed in UI)
        logo_file = st.file_uploader("Upload Logo (For PDF Only)", type=["png", "jpg", "jpeg"])
        if logo_file is not None:
            logo_bytes = logo_file.read()
            logo_base64 = base64.b64encode(logo_bytes).decode('utf-8')
            logo_mime = logo_file.type
            # This HTML is passed to the PDF, but NOT shown in the UI
            logo_img_html = f'<img src="data:{logo_mime};base64,{logo_base64}" alt="Logo">'
        else:
            # If no file is uploaded, we fall back to the 🎯 icon in the PDF
            logo_img_html = '<div style="color: #FF4B4B; font-size: 2.5em; margin-right: 10px;">🎯</div>'

        analyze_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    if analyze_button:
        if not all([target_url, keywords, locations]):
            st.error("Please fill in all required fields before running the analysis.")
            return
        
        st.session_state.start_time = time.time()
        
        with st.spinner("🔍 Analyzing search rankings..."):
            # Process inputs
            keyword_list = [k.strip() for k in keywords.split('\n') if k.strip()]
            location_list = [l.strip() for l in locations.split('\n') if l.strip()]
            
            # Process locations
            processed_locations = []
            invalid_locations = []
            for loc in location_list:
                loc = loc.strip()
                if not loc:  # Skip empty lines
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

            # Validate locations with progress bar
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
                        
                        # Determine which were skipped in this chunk
                        for loc in chunk:
                          
