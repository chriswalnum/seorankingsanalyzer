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

# Page config
st.set_page_config(
    page_title="SEO Rankings Analyzer Pro",
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
def validate_location(location):
    """Validate if a location exists using GeoPy"""
    geolocator = Nominatim(user_agent="seo_analysis_tool")
    try:
        search_term = f"{location['city']}, {location['state']}, USA"
        location_data = geolocator.geocode(search_term)
        time.sleep(1)
        return location_data is not None
    except Exception:
        return False

def fetch_serp_data(query):
    """Fetch SERP data from ValueSERP API"""
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
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

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
            /* ... (keep existing styles) ... */
            
            /* Add these new table styles */
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 2rem 0;
                font-size: 14px;
            }
            th, td {
                padding: 8px;
                border: 1px solid #e2e8f0;
                text-align: center;
            }
            th {
                background: #f8fafc;
                font-weight: 600;
                white-space: nowrap;
            }
            tr:nth-child(even) {
                background-color: #f8fafc;
            }
            .location-cell {
                text-align: left;
                font-weight: 500;
                background-color: #f8fafc;
            }
            .ranking-cell {
                font-family: monospace;
            }
            .n-a {
                color: #666;
                font-style: italic;
            }
        </style>
    </head>
    <body>
        <!-- ... (keep header and metrics sections) ... -->

        <h2>Rankings Overview</h2>
        <table>
            <thead>
                <tr>
                    <th>Location</th>
                    {% for keyword in keywords %}
                    <th>{{ keyword }}</th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for location in locations %}
                <tr>
                    <td class="location-cell">{{ location }}</td>
                    {% for keyword in keywords %}
                    <td class="ranking-cell">
                        {% set position = ranking_matrix.get((location, keyword), 'n/a') %}
                        {% if position == 'n/a' %}
                        <span class="n-a">n/a</span>
                        {% elif '#' in position %}
                        <span class="ranking-good">{{ position }}</span>
                        {% else %}
                        <span class="ranking-bad">{{ position }}</span>
                        {% endif %}
                    </td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <!-- ... (keep footer) ... -->
    </body>
    </html>
    """
    
    # Process data for the template
    keywords = sorted(set(r['keyword'] for r in results))
    locations = sorted(set(r['location'] for r in results))
    
    # Create ranking matrix
    ranking_matrix = {(r['location'], r['keyword']): r['target_position'] for r in results}
    
    template = jinja2.Template(template_string)
    total_queries = len(results)
    ranked_queries = len([r for r in results if '#' in r['target_position']])
    ranking_rate = f"{(ranked_queries/total_queries*100):.1f}"
    
    html_report = template.render(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        target_url=target_url,
        total_queries=total_queries,
        ranked_queries=ranked_queries,
        ranking_rate=ranking_rate,
        results=results,
        keywords=keywords,
        locations=locations,
        ranking_matrix=ranking_matrix
    )
    
    return html_report
def main():
    # Header with professional styling
    st.title("🎯 SEO Rankings Analyzer Pro")
    st.markdown("""
        <div class="info-box">
            Analyze your website's search rankings across multiple locations with detailed insights and professional reporting.
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
        st.markdown("Enter locations in City, State format, one per line")
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
            for loc in location_list:
                parts = [p.strip() for p in loc.split(',')]
                if len(parts) == 2:
                    processed_locations.append({
                        'city': parts[0],
                        'state': parts[1].strip()
                    })

            # Validate locations with progress bar
            with st.expander("📍 Location Validation Progress", expanded=True):
                progress_text = st.empty()
                progress_bar = st.progress(0)
                valid_locations = []
                for i, loc in enumerate(processed_locations):
                    progress_text.text(f"Validating {loc['city']}, {loc['state']}...")
                    if validate_location(loc):
                        valid_locations.append(loc)
                    progress_bar.progress((i + 1) / len(processed_locations))

            if not valid_locations:
                st.error("❌ No valid locations provided. Please check your location format and try again.")
                return

            # Create search queries
            search_queries = []
            for location in valid_locations:
                location_string = f"{location['city']}, {location['state']}"
                for keyword in keyword_list:
                    search_queries.append({
                        'keyword': keyword,
                        'location': location_string,
                        'query': f"{keyword} {location_string}"
                    })

            # Analyze rankings with detailed progress tracking
            with st.expander("🔍 Rankings Analysis Progress", expanded=True):
                progress_text = st.empty()
                progress_bar = st.progress(0)
                results = []
                for i, query in enumerate(search_queries):
                    progress_text.text(f"Analyzing '{query['keyword']}' in {query['location']}...")
                    serp_data = fetch_serp_data(query)
                    if serp_data:
                        organic_results = serp_data.get('organic_results', [])
                        local_results = serp_data.get('local_results', [])
                        
                        position = "Not on Page 1"
                        for idx, result in enumerate(organic_results, 1):
                            if target_url in result.get('domain', '').lower():
                                position = f"#{idx}"
                                break
                        
                        results.append({
                            'keyword': query['keyword'],
                            'location': query['location'],
                            'target_position': position,
                            'organic_results': organic_results[:3],
                            'local_results': local_results[:3]
                        })
                    progress_bar.progress((i + 1) / len(search_queries))

            analysis_duration = round(time.time() - st.session_state.start_time, 1)
            st.session_state.results = results
            st.session_state.analysis_complete = True
            st.session_state.analysis_duration = analysis_duration

    # Display results if analysis is complete
    if st.session_state.analysis_complete and hasattr(st.session_state, 'results'):
        results = st.session_state.results
        
        # Summary metrics with enhanced styling
        st.markdown("### 📊 Analysis Summary")
        col1, col2, col3 = st.columns(3)
        total_queries = len(results)
        ranked_queries = len([r for r in results if '#' in r['target_position']])
        
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

        # Rankings overview with enhanced styling
        st.markdown("### 📈 Rankings Overview")
        df_overview = pd.DataFrame(results)
        
        # Create pivot table
        pivot_data = df_overview.pivot(
            index='location',
            columns='keyword',
            values='target_position'
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

        # Export options
        st.subheader("📥 Export Options")
        col1, col2, col3 = st.columns(3)
        
        # Generate HTML report
        html_report = generate_html_report(results, target_url)
        
        with col1:
            st.download_button(
                label="📄 Download HTML Report",
                data=html_report,
                file_name="seo_analysis_report.html",
                mime="text/html"
            )
        
        with col2:
            csv = df_overview.to_csv(index=False)
            st.download_button(
                label="📊 Download CSV",
                data=csv,
                file_name="seo_analysis.csv",
                mime="text/csv"
            )
        
        with col3:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df_overview.to_excel(writer, sheet_name='Rankings', index=False)
            excel_data = excel_buffer.getvalue()
            st.download_button(
                label="📘 Download Excel",
                data=excel_data,
                file_name="seo_analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main()    
