# SEO Rankings Analyzer

A Streamlit-based tool that analyzes search engine rankings across multiple locations and keywords. Built with Python and the ValueSERP API, this tool helps track and visualize search rankings for websites.

## Features

- Track website rankings for multiple keywords
- Analyze rankings across different locations
- View organic search results
- Monitor Google Maps/Local Pack rankings
- Export results to CSV or Excel
- Real-time location validation
- Interactive data visualization

## Requirements

- Python 3.7+
- Streamlit
- ValueSERP API key
- Other dependencies listed in requirements.txt

## Installation

1. Clone this repository
2. Install required packages:
```bash
pip install -r requirements.txt
```
3. Set up your ValueSERP API key in Streamlit Secrets

## Usage

1. Enter your target website URL
2. Add keywords (one per line)
3. Add locations in "City, State" format (one per line)
4. Click "Run Analysis"
5. View results in the interactive dashboard
6. Export data as needed

## Data Sources

This tool uses the ValueSERP API to fetch search engine results data. Rankings are checked for both organic search results and the Google Maps section.

## Privacy & Security

- API keys should be stored in Streamlit Secrets
- No user data is stored
- All analysis is performed in real-time

## Development Status

This is a beta version. Features and interface may change as the tool evolves.

## Acknowledgments

Built using:
- Streamlit
- ValueSERP API
- Pandas
- GeoPy

## Contact

Chris Walnum
