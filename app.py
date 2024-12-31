# Version 1.4.0
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
    # Add debug prefix for easy identification in logs
    debug_prefix = "[Location Validation]"
    
    print(f"{debug_prefix} Starting validation for input: {location}")
    
    geolocator = Nominatim(user_agent="seo_analysis_tool")
    try:
        # Log input type and value
        print(f"{debug_prefix} Input type: {type(location)}")
        
        # Check if input is a ZIP code (5 digits)
        if isinstance(location, str) and location.isdigit() and len(location) == 5:
            search_term = f"{location}, USA"
            print(f"{debug_prefix} Processing as ZIP code")
        else:  # city_state dict
            search_term = f"{location['city']}, {location['state']}, USA"
            print(f"{debug_prefix} Processing as City/State pair")
            
        print(f"{debug_prefix} Search term: {search_term}")
        
        # Log before geocoding attempt
        print(f"{debug_prefix} Attempting geocoding...")
        
        # Wait for rate limiter before making request
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
    
    # Create a thread-safe lock for updating progress
    progress_lock = threading.Lock()
    
    def update_progress():
        nonlocal completed
        with progress_lock:
            completed += 1
            progress = completed / total
            progress_bar.progress(progress)
            progress_text.text(f"Processed {completed}/{total} queries...")
    
    # Use ThreadPoolExecutor for parallel processing
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

def generate_html_report(results, target_url):
    """Generate a professional HTML report using Jinja2"""
    template_string = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SEO Analysis Report</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 0 auto;
                padding: 2rem;
                max-width: 1200px;
                background-color: #f8fafc;
            }
            .container {
                background: white;
                padding: 2rem;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .header {
                text-align: center;
                margin-bottom: 2rem;
            }
            .header h1 {
                color: #1e3a8a;
                font-size: 24px;
                margin-bottom: 8px;
            }
            .header p {
                color: #64748b;
                margin: 4px 0;
            }
            .metrics {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1rem;
                margin-bottom: 2rem;
            }
            .metric-card {
                background: #f8fafc;
                padding: 1rem;
                border-radius: 6px;
                text-align: center;
            }
            .section-title {
                color: #1e3a8a;
                font-size: 28px;
                margin: 2rem 0 1rem 0;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid #e2e8f0;
            }
            .keyword-table {
                margin-bottom: 2rem;
                page-break-inside: avoid;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 1rem 0;
                font-size: 16px;
                background: white;
            }
            th, td {
                padding: 8px 12px;
                border: 1px solid #e2e8f0;
            }
            .competitor-rank {
                text-align: center;
                color: #64748b;
                font-weight: 500;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>SEO Rankings Analysis Report</h1>
                <p>{{ target_url }}</p>
                <p>Generated on {{ timestamp }}</p>
            </div>

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
        <div class="section-title">Local Rankings Overview</div>
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
        </div>
    </body>
    </html>
    """
    
    # Process data for template
    keywords = sorted(set(r['keyword'] for r in results))
    locations = sorted(set(r['location'] for r in results))
    
    # Create ranking matrix
    ranking_matrix = {(r['location'], r['keyword']): r['target_position'] for r in results}
    
    # Process competitor data
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
    
    # Process local business data
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
    total_local_listings = len([r for r in results if r['local_results']])
    in_top_3_local = len([r for r in results if any(
        business.get('title', '').lower() == target_url.lower() 
        for business in r.get('local_results', [])[:3]
    )])
    local_rate = f"{(in_top_3_local / total_local_listings * 100):.1f}" if total_local_listings > 0 else "0.0"

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
        local_rate=local_rate
    )
    
    return html_report

def main():
    # Get version number from first line comment
    with open(__file__, 'r') as file:
        first_line = file.readline().strip()
        version = first_line.replace('# Version ', '')

    # Header with professional styling
    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        st.markdown("""
            <div style="display: flex; align-items: center; margin-bottom: 20px;">
                <div style="color: #FF4B4B; font-size: 2.5em; margin-right: 10px;">🎯</div>
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

    # Sidebar for inputs with improved UX
    with st.sidebar:
        st.header("Analysis Configuration")
        
        # Target URL input with validation
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

        analyze_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)

    # Main content area with improved error handling and progress tracking
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
                    
                # Check if it's a ZIP code
                if loc.isdigit():
                    if len(loc) == 5:
                        processed_locations.append(loc)  # Store ZIP code as string
                    else:
                        invalid_locations.append(f"• {loc} (invalid ZIP code - must be 5 digits)")
                # Check if it's City, State format
                else:
                    parts = [p.strip() for p in loc.split(',')]
                    if len(parts) == 2:
                        processed_locations.append({
                            'city': parts[0],
                            'state': parts[1].strip()
                        })
                    else:
                        invalid_locations.append(f"• {loc} (invalid format - use 'City, State' or 5-digit ZIP)")

            # Show error message for invalid locations and stop processing
            if invalid_locations:
                error_message = """Invalid location formats detected:

{}

Please use either:
- City, State (e.g., New York, NY)
- ZIP code (e.g., 90210)

Please correct all location formats before running the analysis."""

                # Join invalid locations with explicit newlines
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
                
                # Process location validation in parallel
                skipped_locations = []  # Track skipped locations
                with ThreadPoolExecutor(max_workers=3) as executor:
                    chunk_size = max(1, len(processed_locations) // 3)
                    location_chunks = [processed_locations[i:i + chunk_size] 
                                    for i in range(0, len(processed_locations), chunk_size)]
                    
                    future_to_chunk = {executor.submit(validate_location_batch, chunk): i 
                                     for i, chunk in enumerate(location_chunks)}
                    
                    completed_chunks = 0
                    for future in as_completed(future_to_chunk):
                        chunk_valid_locations = future.result()
                        
                        # Check which locations were skipped in this chunk
                        chunk_index = future_to_chunk[future]
                        chunk = location_chunks[chunk_index]
                        for loc in chunk:
                            if isinstance(loc, str):  # ZIP code
                                if loc not in [str(x) if isinstance(x, str) else None for x in chunk_valid_locations]:
                                    skipped_locations.append(loc)
                            else:  # city_state
                                loc_str = f"{loc['city']}, {loc['state']}"
                                if loc not in chunk_valid_locations:
                                    skipped_locations.append(loc_str)
                        
                        valid_locations.extend(chunk_valid_locations)
                        completed_chunks += 1
                        progress_bar.progress(completed_chunks / len(location_chunks))
                        progress_text.text(f"Validated {completed_chunks}/{len(location_chunks)} location groups...")
                
                # Show warning about skipped locations
                if skipped_locations:
                    warning_locations = "\n• ".join(skipped_locations)
                    st.warning(f"""The following locations could not be validated and will be skipped:
- {warning_locations}

Please check for typos or verify these locations exist.""")
                    
                # Only continue if we have at least one valid location
                if not valid_locations:
                    st.error("No valid locations found. Please check your inputs and try again.")
                    return

# Create search queries
            search_queries = []
            for location in valid_locations:
                if isinstance(location, str):  # ZIP code
                    location_string = location
                else:  # city_state dict
                    location_string = f"{location['city']}, {location['state']}"
                
                for keyword in keyword_list:
                    search_queries.append({
                        'keyword': keyword,
                        'location': location_string,
                        'query': f"{keyword} {location_string}"
                    })

            # Analyze rankings with parallel processing
            with st.expander("🔍 Rankings Analysis Progress", expanded=True):
                progress_text = st.empty()
                progress_bar = st.progress(0)
                results = parallel_process_queries(search_queries, target_url, progress_text, progress_bar)

            analysis_duration = round(time.time() - st.session_state.start_time, 1)
            st.session_state.results = results
            st.session_state.analysis_complete = True
            st.session_state.analysis_duration = analysis_duration
            
            # Add timing information
            st.info(f"✨ Analysis completed in {analysis_duration} seconds")

    # Display results if analysis is complete
    if st.session_state.analysis_complete and hasattr(st.session_state, 'results'):
        results = st.session_state.results
        
        # Summary metrics with enhanced styling
        st.markdown("### 📊 Analysis Summary")
        col1, col2, col3 = st.columns(3)
        total_queries = len(results)
        ranked_queries = len([r for r in results if '#' in r['target_position']])
        
        # Local metrics calculation
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

        # Rankings overview with enhanced styling
        st.markdown("### 📈 Rankings Overview")
        df_overview = pd.DataFrame(results)
        
        # Create pivot table with aggregation that takes minimum rank
        pivot_data = pd.pivot_table(
            df_overview,
            index='location',
            columns='keyword',
            values='target_position',
            aggfunc=lambda x: max(x, key=lambda y: float('inf') if y == 'Not on Page 1' else float(y.replace('#', '')))
        )
        
        # Style the dataframe
        def style_ranking(val):
            if '#' in str(val):
                return 'background-color: #dcfce7; color: #166534'
            return 'background-color: #fee2e2; color: #991b1b'
        
        styled_pivot = pivot_data.style.applymap(style_ranking)
        st.dataframe(styled_pivot, height=400)

        # Detailed results in tabs
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

# Generate HTML report
        html_report = generate_html_report(results, target_url)

        # Export options
        st.subheader("📥 Export Options")
        col1, col2, col3 = st.columns(3)
        
        # Clean domain name for filename
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
