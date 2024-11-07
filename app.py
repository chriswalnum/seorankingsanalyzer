import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import pytz
from geopy.geocoders import Nominatim

# Page config
st.set_page_config(
    page_title="SEO Rankings Analyzer",
    page_icon="📊",
    layout="wide"
)

# Custom CSS
st.markdown("""
    <style>
        .stApp {
            max-width: 1200px;
            margin: 0 auto;
        }
        .metric-card {
            background-color: #f0f7ff;
            padding: 20px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .results-table {
            font-size: 14px;
        }
        .status-badge {
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
        }
        .status-success {
            background-color: #e1f5e1;
            color: #2d862d;
        }
        .status-failure {
            background-color: #ffe6e6;
            color: #cc0000;
        }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False

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

def fetch_serp_data(query, api_key):
    """Fetch SERP data from ValueSERP API"""
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
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def main():
    # Header
    st.title("SEO Rankings Analyzer 📊")
    st.markdown("Analyze your website's search rankings across multiple locations")

    # Sidebar for inputs
    with st.sidebar:
        st.header("Configuration")
        
        # API Key input - using Streamlit secrets if available
        default_api_key = st.secrets["VALUESERP_API_KEY"] if "VALUESERP_API_KEY" in st.secrets else ""
        api_key = st.text_input("ValueSERP API Key", 
                               value=default_api_key,
                               type="password")
        
        # Target URL input
        target_url = st.text_input("Target Website URL", 
                                  placeholder="example.com")
        if target_url:
            target_url = target_url.replace('http://', '').replace('https://', '').replace('www.', '').rstrip('/')

        # Keywords input
        keywords = st.text_area("Keywords (one per line)", 
                              placeholder="hvac installation\nboiler replacement")
        
        # Locations input
        locations = st.text_area("Locations (City, State - one per line)", 
                               placeholder="Manchester, CT\nBolton, CT")

        analyze_button = st.button("Run Analysis", type="primary")

    # Main content area
    if analyze_button and api_key and target_url and keywords and locations:
        with st.spinner("Analyzing search rankings..."):
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

            # Validate locations
            st.write("Validating locations...")
            progress_bar = st.progress(0)
            valid_locations = []
            for i, loc in enumerate(processed_locations):
                if validate_location(loc):
                    valid_locations.append(loc)
                progress_bar.progress((i + 1) / len(processed_locations))

            if not valid_locations:
                st.error("No valid locations provided.")
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

            # Analyze rankings
            results = []
            progress_bar = st.progress(0)
            for i, query in enumerate(search_queries):
                serp_data = fetch_serp_data(query, api_key)
                if serp_data:
                    organic_results = serp_data.get('organic_results', [])
                    local_results = serp_data.get('local_results', [])
                    
                    # Find target URL position
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

            st.session_state.results = results
            st.session_state.analysis_complete = True

    # Display results if analysis is complete
    if st.session_state.analysis_complete and hasattr(st.session_state, 'results'):
        results = st.session_state.results
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        total_queries = len(results)
        ranked_queries = len([r for r in results if '#' in r['target_position']])
        
        with col1:
            st.metric("Total Queries", total_queries)
        with col2:
            st.metric("First Page Rankings", ranked_queries)
        with col3:
            st.metric("Ranking Rate", f"{(ranked_queries/total_queries*100):.1f}%")

        # Rankings overview
        st.subheader("Rankings Overview")
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
                return 'background-color: #e1f5e1; color: #2d862d'
            return 'background-color: #ffe6e6; color: #cc0000'
        
        styled_pivot = pivot_data.style.applymap(style_ranking)
        st.dataframe(styled_pivot, height=400)

        # Detailed results in tabs
        tab1, tab2 = st.tabs(["Organic Results", "Local Results"])
        
        with tab1:
            for result in results:
                with st.expander(f"{result['keyword']} - {result['location']}"):
                    for idx, org in enumerate(result['organic_results'], 1):
                        st.markdown(f"**#{idx}** - {org.get('title', 'N/A')}")
                        st.markdown(f"Domain: {org.get('domain', 'N/A')}")
                        st.markdown("---")

        with tab2:
            for result in results:
                with st.expander(f"{result['keyword']} - {result['location']}"):
                    for idx, loc in enumerate(result['local_results'], 1):
                        st.markdown(f"**#{idx}** - {loc.get('title', 'N/A')}")
                        st.markdown(f"Rating: {loc.get('rating', 'N/A')}★ ({loc.get('reviews', '0')} reviews)")
                        st.markdown("---")

        # Export options
        st.subheader("Export Options")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Download CSV"):
                csv = df_overview.to_csv(index=False)
                st.download_button(
                    label="Download CSV File",
                    data=csv,
                    file_name="seo_analysis.csv",
                    mime="text/csv"
                )
        with col2:
            if st.button("Download Excel"):
                # Convert DataFrame to Excel
                buffer = pd.ExcelWriter('seo_analysis.xlsx', engine='xlsxwriter')
                df_overview.to_excel(buffer, index=False)
                buffer.close()

                # Offer download
                with open('seo_analysis.xlsx', 'rb') as f:
                    excel_data = f.read()
                st.download_button(
                    label="Download Excel File",
                    data=excel_data,
                    file_name="seo_analysis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

if __name__ == "__main__":
    main()
