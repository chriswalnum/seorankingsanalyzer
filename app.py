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
        
@sleep_and_retry
@limits(calls=5, period=1)
def rate_limited_api_call(base_url, params):
    """Make a rate-limited API call"""
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    return response.json()

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
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 0 auto;
                padding: 2rem;
                max-width: 800px;
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
            .metric-card h3 {
                font-size: 14px;
                color: #64748b;
                margin: 0 0 8px 0;
            }
            .metric-value {
                font-size: 24px;
                font-weight: bold;
                color: #1e3a8a;
            }
            .section-title {
                color: #1e3a8a;
                font-size: 18px;
                margin: 2rem 0 1rem 0;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid #e2e8f0;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 1rem 0;
                font-size: 14px;
                background: white;
            }
            th, td {
                padding: 8px 12px;
                border: 1px solid #e2e8f0;
            }
            th {
                background: #f1f5f9;
                font-weight: 600;
                text-align: left;
                color: #1e293b;
            }
            .location-cell {
                font-weight: 500;
            }
            .ranking-good {
                color: #166534;
                background: #dcfce7;
                padding: 2px 6px;
                border-radius: 4px;
                font-weight: 500;
            }
            .ranking-bad {
                color: #991b1b;
                background: #fee2e2;
                padding: 2px 6px;
                border-radius: 4px;
                font-weight: 500;
            }
            .competitors-table {
                margin-top: 2rem;
            }
            .competitor-rank {
                color: #64748b;
                font-weight: 500;
                text-align: center;
                width: 60px;
            }
            .footer {
                text-align: center;
                margin-top: 2rem;
                color: #64748b;
                font-size: 12px;
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

            <div class="section-title">Rankings Overview</div>
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
                        <td style="text-align: center">
                            {% set position = ranking_matrix.get((location, keyword), 'n/a') %}
                            {% if position == 'n/a' %}
                            <span style="color: #94a3b8">-</span>
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
        </div>
    </body>
    </html>
    """
    
    # Process data for the template
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
            
        # Get unique competitors across all locations for this keyword
        competitors = result['organic_results'][:3]
        for rank, comp in enumerate(competitors, 1):
            competitor_data[keyword].append({
                'rank': rank,
                'domain': comp.get('domain', 'N/A'),
                'location': result['location']
            })
    
    template = jinja2.Template(template_string)
    total_queries = len(results)
    ranked_queries = len([r for r in results if '#' in r['target_position']])
    ranking_rate = f"{(ranked_queries/total_queries*100):.1f}"
    
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
        competitor_data=competitor_data
    )
    
    return html_report

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

def main():
    # Header with professional styling
    st.title("🎯 SEO Rankings Analyzer Pro")
    st.markdown("""
        <div class="info-box">
            Analyze a website's search rankings across multiple locations with detailed insights.
        </div>
    """, unsafe_allow_html=True)

    # [... rest of your main code ...]

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

        # [... rest of your results display code ...]

if __name__ == "__main__":
    main()
