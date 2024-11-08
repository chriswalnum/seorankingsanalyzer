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

def generate_html_report(results, target_url, analysis_duration):
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
                max-width: 1200px;
                margin: 0 auto;
                padding: 2rem;
            }
            .header {
                text-align: center;
                padding: 2rem;
                background: #f8fafc;
                border-radius: 8px;
                margin-bottom: 2rem;
            }
            .metrics {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1rem;
                margin-bottom: 2rem;
            }
            .metric-card {
                background: #fff;
                padding: 1.5rem;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                text-align: center;
            }
            .metric-value {
                font-size: 2rem;
                font-weight: bold;
                color: #3b82f6;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 2rem 0;
            }
            th, td {
                padding: 0.75rem;
                border: 1px solid #e2e8f0;
            }
            th {
                background: #f8fafc;
                font-weight: 600;
            }
            .ranking-good {
                color: #166534;
                background: #dcfce7;
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
            }
            .ranking-bad {
                color: #991b1b;
                background: #fee2e2;
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
            }
            .footer {
                text-align: center;
                margin-top: 3rem;
                padding-top: 2rem;
                border-top: 1px solid #e2e8f0;
                color: #64748b;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>SEO Rankings Analysis Report</h1>
            <p>Generated on {{ timestamp }}</p>
            <p>Target URL: {{ target_url }}</p>
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
            <div class="metric-card">
                <h3>Analysis Duration</h3>
                <div class="metric-value">{{ analysis_duration }}s</div>
            </div>
        </div>

        <h2>Rankings Overview</h2>
        <table>
            <thead>
                <tr>
                    <th>Location</th>
                    <th>Keyword</th>
                    <th>Position</th>
                    <th>Top Competitor</th>
                </tr>
            </thead>
            <tbody>
                {% for result in results %}
                <tr>
                    <td>{{ result.location }}</td>
                    <td>{{ result.keyword }}</td>
                    <td>
                        {% if '#' in result.target_position %}
                        <span class="ranking-good">{{ result.target_position }}</span>
                        {% else %}
                        <span class="ranking-bad">{{ result.target_position }}</span>
                        {% endif %}
                    </td>
                    <td>{{ result.organic_results[0].domain if result.organic_results else 'N/A' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="footer">
            <p>Generated using SEO Rankings Analyzer Pro</p>
            <p>Analysis completed in {{ analysis_duration }} seconds</p>
        </div>
    </body>
    </html>
    """
    
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
        analysis_duration=analysis_duration,
        results=results
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

        # Keywords input with example
        st.markdown("### Keywords")
        st.markdown("Enter one keyword per line. Example:")
        st.code("hvac installation\nboiler replacement")
        keywords = st.text_area("", placeholder="Enter your keywords here")
        
        # Locations input with example
        st.markdown("### Locations")
        st.markdown("Enter one location per line (City, State format). Example:")
        st.code("Manchester, CT\nBolton, CT")
        locations = st.text_area("", placeholder="Enter your locations here")

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
        col1, col2, col3, col4 = st.columns(4)
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
        with col4:
            st.markdown(
                f"""<div class="metric-card">
                    <h4>Analysis Duration</h4>
                    <div style="font-size: 24px; font-weight: bold; color: #3b82f6;">
                        {st.session_state.analysis_duration}s
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
        html_report = generate_html_report(results, target_url, st.session_state.analysis_duration)
        
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
