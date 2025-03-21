import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

def update_google_sheet():
    print("Starting Google Sheets update...")
    
    # Find the most recent JSON file
    scraper_results_dir = "scraper_results"
    json_files = [f for f in os.listdir(scraper_results_dir) if f.endswith('.json')]
    if not json_files:
        print("No JSON files found in the scraper_results directory.")
        return
    
    # Sort by date (filename contains date in format: events_findings_YYYYMMDD_HHMMSS.json)
    latest_file = sorted(json_files, reverse=True)[0]
    json_path = os.path.join(scraper_results_dir, latest_file)
    
    print(f"Using most recent data file: {json_path}")
    
    # Load event data
    with open(json_path, 'r', encoding='utf-8') as f:
        event_data = json.load(f)
    
    # Connect to Google Sheets
    # Load from GitHub secrets
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not credentials_json:
        print("Google credentials not found in environment variables.")
        return
    
    # Write credentials to a temporary file
    creds_path = "temp_credentials.json"
    with open(creds_path, 'w') as f:
        f.write(credentials_json)
    
    # Authenticate
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(credentials)
    
    # Open the spreadsheet
    sheet_id = os.environ.get('GOOGLE_SHEET_ID')
    if not sheet_id:
        print("Google Sheet ID not found in environment variables.")
        return
    
    try:
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Clear existing data (keep headers)
        if sheet.row_count > 1:
            sheet.delete_rows(2, sheet.row_count)
        
        # Prepare data for insertion
        rows = []
        for event in event_data:
            rows.append([
                event.get('trust_abbrev', ''),
                event.get('trust_name', ''),
                event.get('trust_site', ''),
                event.get('page_url', ''),
                event.get('title', ''),
                event.get('date', ''),
                event.get('time', ''),
                event.get('location', ''),
                event.get('description', ''),
                event.get('event_url', ''),
                event.get('scan_date', datetime.now().strftime("%Y-%m-%d"))
            ])
        
        # Insert all rows at once
        if rows:
            sheet.append_rows(rows)
            print(f"Successfully updated Google Sheet with {len(rows)} events.")
        else:
            print("No event data to update.")
            
    except Exception as e:
        print(f"Error updating Google Sheet: {e}")
    
    # Clean up
    if os.path.exists(creds_path):
        os.remove(creds_path)

if __name__ == "__main__":
    update_google_sheet()
