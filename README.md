# SEO Rankings Analyzer Pro

A professional SEO analysis tool built with Streamlit that helps analyze website rankings across multiple locations and keywords.

## Features

- 🌐 Multi-location ranking analysis
- 🔍 Keyword position tracking
- 📊 Interactive data visualization
- 📍 Local SEO results tracking
- 📑 Professional HTML report generation
- 📤 Multiple export options (HTML, CSV, Excel)
- 📈 Real-time analysis progress tracking

## Setup

1. Clone the repository:
```bash
git clone https://github.com/chriswalnum/seorankingsanalyzer.git
cd seorankingsanalyzer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure Streamlit secrets:
Create a `.streamlit/secrets.toml` file with your ValueSERP API key:
```toml
VALUESERP_API_KEY = "your-api-key-here"
```

4. Run the application:
```bash
streamlit run app.py
```

## Usage

1. Enter your target website URL
2. Add keywords (one per line)
3. Add locations in "City, State" format (one per line)
4. Click "Run Analysis"
5. View results and download reports in your preferred format

## Security Notes

- API key is stored securely in Streamlit secrets
- Location validation prevents misuse
- Rate limiting implemented for API calls

## Output Formats

- HTML Report: Professional, styled report with all analysis details
- CSV: Raw data export for further analysis
- Excel: Formatted spreadsheet with analysis results

## License

MIT License
