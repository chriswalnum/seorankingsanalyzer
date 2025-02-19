# Version 1.5.0
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
                <div
