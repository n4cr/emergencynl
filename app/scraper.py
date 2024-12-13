import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sqlite3
import logging
import time
from typing import Optional, List, Dict, Tuple
import argparse
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class P2000Scraper:
    BASE_URL = "https://p2000-online.net/p2000.py"
    MAX_CONSECUTIVE_ERRORS = 3
    MAX_EMPTY_PAGES = 2
    
    def __init__(self, db_path: str = os.path.join('data', 'p2000.db'), delay: float = 1.0):
        self.db_path = db_path
        self.delay = delay
        self.consecutive_errors = 0
        self.empty_pages = 0
        self.setup_database()
    
    def setup_database(self):
        """Create the database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    service_type TEXT NOT NULL,
                    region TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    raw_timestamp TEXT NOT NULL,
                    UNIQUE(timestamp, service_type, region, message)
                )
            """)
            conn.commit()
    
    def parse_datetime(self, date_str: str) -> Optional[datetime]:
        """Parse the P2000 datetime string into a datetime object."""
        try:
            if not date_str or not date_str.strip():
                return None
            return datetime.strptime(date_str.strip(), "%d-%m-%Y %H:%M:%S")
        except ValueError:
            return None
    
    def scrape_page(self, page: int) -> List[Dict]:
        """Scrape a single page of P2000 data."""
        # Add delay before making the request
        time.sleep(self.delay)
        
        params = {
            "pagina": page,
            "aantal": 30  # Number of items per page
        }
        
        try:
            response = requests.get(self.BASE_URL, params=params)
            
            # Check for server error
            if response.status_code == 500:
                self.consecutive_errors += 1
                logging.warning(f"Server error (500) on page {page}. Consecutive errors: {self.consecutive_errors}")
                
                if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                    logging.error(f"Reached maximum consecutive errors ({self.MAX_CONSECUTIVE_ERRORS}). Stopping scraper.")
                    return []
                
                return []  # Skip this page and continue with the next
            
            # Reset error counter on successful request
            self.consecutive_errors = 0
            
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Find all tables
            tables = soup.find_all('table')
            
            # Find the main data table
            main_table = None
            for table in tables:
                # Look for the table that has rows with the expected incident structure
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 4:
                        # Check if this row has the expected classes (DT, Am/Br/Po, Regio, Md)
                        if any(cell.get('class', []) for cell in cells):
                            main_table = table
                            break
                if main_table:
                    break
            
            if not main_table:
                logging.warning(f"Could not find main data table on page {page}")
                return []
            
            incidents = []
            current_incident = None
            
            # Group rows that belong to the same incident
            rows = main_table.find_all('tr')
            i = 0
            while i < len(rows):
                row = rows[i]
                cells = row.find_all('td')
                
                # Main incident row (has 4 cells)
                if len(cells) == 4:
                    timestamp = cells[0].text.strip()
                    
                    # Only process rows with valid timestamps
                    if timestamp and self.parse_datetime(timestamp):
                        if current_incident:
                            incidents.append(current_incident)
                        
                        current_incident = {
                            'timestamp': timestamp,
                            'service_type': cells[1].text.strip(),
                            'region': cells[2].text.strip(),
                            'message': cells[3].text.strip(),
                            'details': []
                        }
                        
                        # Look ahead for detail rows
                        j = i + 1
                        while j < len(rows):
                            detail_row = rows[j]
                            detail_cells = detail_row.find_all('td')
                            
                            # Detail row has 4 cells with first 3 empty
                            if len(detail_cells) == 4 and all(not c.text.strip() for c in detail_cells[:3]):
                                detail = detail_cells[3].text.strip()
                                if detail:
                                    current_incident['details'].append(detail)
                                j += 1
                            # Detail row has 3 cells with first 2 empty
                            elif len(detail_cells) == 3 and all(not c.text.strip() for c in detail_cells[:2]):
                                detail = detail_cells[2].text.strip()
                                if detail:
                                    current_incident['details'].append(detail)
                                j += 1
                            else:
                                break
                        
                        i = j - 1  # Update main loop counter to skip processed detail rows
                
                i += 1
            
            # Add the last incident if exists
            if current_incident:
                incidents.append(current_incident)
            
            # Validate number of incidents
            if len(incidents) < 30 and page == 1:  # First page should always have 30 incidents
                logging.warning(f"Found only {len(incidents)} incidents on page {page} (expected 30)")
            
            return incidents
            
        except requests.RequestException as e:
            if "500" in str(e):
                self.consecutive_errors += 1
                logging.warning(f"Server error (500) on page {page}. Consecutive errors: {self.consecutive_errors}")
                
                if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                    logging.error(f"Reached maximum consecutive errors ({self.MAX_CONSECUTIVE_ERRORS}). Stopping scraper.")
                    return []
            else:
                logging.error(f"Error fetching page {page}: {str(e)}")
            return []
    
    def store_incidents(self, incidents: List[Dict]) -> int:
        """Store incidents in the database, avoiding duplicates."""
        stored_count = 0
        
        with sqlite3.connect(self.db_path) as conn:
            for incident in incidents:
                try:
                    timestamp = self.parse_datetime(incident['timestamp'])
                    if timestamp:  # Only store incidents with valid timestamps
                        conn.execute("""
                            INSERT OR IGNORE INTO incidents 
                            (timestamp, service_type, region, message, details, raw_timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            timestamp,
                            incident['service_type'],
                            incident['region'],
                            incident['message'],
                            '\n'.join(incident['details']),
                            incident['timestamp']
                        ))
                        
                        if conn.total_changes > 0:
                            stored_count += 1
                            
                except sqlite3.Error as e:
                    logging.error(f"Database error: {str(e)}")
                except Exception as e:
                    logging.error(f"Error processing incident: {str(e)}")
            
            conn.commit()
        
        return stored_count
    
    def scrape_until_date(self, from_date: datetime) -> Tuple[int, int]:
        """
        Scrape P2000 data until reaching the specified date.
        Returns tuple of (total_incidents, new_incidents).
        """
        page = 1
        total_incidents = 0
        new_incidents = 0
        reached_date = False
        
        while not reached_date:
            logging.info(f"Scraping page {page}...")
            incidents = self.scrape_page(page)
            
            # Check if we need to stop due to too many errors
            if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                logging.warning("Stopping scraper due to too many consecutive server errors.")
                break
            
            if not incidents:
                if self.consecutive_errors > 0:
                    # If it's a server error, try the next page
                    page += 1
                    continue
                else:
                    # If it's not a server error (empty page), stop scraping
                    logging.info("No more incidents found.")
                    break
            
            # Check if we've reached the target date
            for incident in incidents:
                incident_date = self.parse_datetime(incident['timestamp'])
                if incident_date and incident_date < from_date:
                    reached_date = True
                    break
            
            stored = self.store_incidents(incidents)
            total_incidents += len(incidents)
            new_incidents += stored
            
            logging.info(f"Processed {len(incidents)} incidents, {stored} new")
            
            # Track empty pages (no new incidents)
            if stored == 0:
                self.empty_pages += 1
                if self.empty_pages >= self.MAX_EMPTY_PAGES:
                    logging.info(f"Stopping after {self.MAX_EMPTY_PAGES} pages with no new incidents")
                    break
            else:
                self.empty_pages = 0
            
            if not reached_date:
                page += 1
        
        return total_incidents, new_incidents

def parse_date(date_str: str) -> datetime:
    """Parse date string in various formats."""
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(
        "Invalid date format. Please use one of: "
        "YYYY-MM-DD, DD-MM-YYYY, YYYY/MM/DD, DD/MM/YYYY"
    )

def main():
    parser = argparse.ArgumentParser(
        description="P2000 Emergency Services Data Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape data from the last 24 hours
  python scraper.py --days 1
  
  # Scrape data from the last 6 hours
  python scraper.py --hours 6

  # Scrape data from the last 30 minutes
  python scraper.py --minutes 30
  
  # Scrape data from a specific date
  python scraper.py --from-date 2024-01-01
  
  # Scrape data to a specific database file
  python scraper.py --days 7 --db-path custom.db
  
  # Scrape with custom delay between requests
  python scraper.py --days 1 --delay 2.5
  
  # Scrape with debug logging
  python scraper.py --days 1 --debug
        """
    )
    
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        '--days',
        type=int,
        help='Number of days to scrape from today'
    )
    date_group.add_argument(
        '--hours',
        type=int,
        help='Number of hours to scrape from now'
    )
    date_group.add_argument(
        '--minutes',
        type=int,
        help='Number of minutes to scrape from now'
    )
    date_group.add_argument(
        '--from-date',
        type=str,
        help='Start date (format: YYYY-MM-DD or DD-MM-YYYY)'
    )
    
    parser.add_argument(
        '--db-path',
        type=str,
        default='p2000.db',
        help='Path to SQLite database file (default: p2000.db)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay in seconds between requests (default: 1.0)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Calculate from_date
        if args.days:
            from_date = datetime.now() - timedelta(days=args.days)
        elif args.hours:
            from_date = datetime.now() - timedelta(hours=args.hours)
        elif args.minutes:
            from_date = datetime.now() - timedelta(minutes=args.minutes)
        else:
            from_date = parse_date(args.from_date)
        
        # Initialize scraper and run
        scraper = P2000Scraper(db_path=args.db_path, delay=args.delay)
        total, new = scraper.scrape_until_date(from_date)
        
        # Print summary
        print("\nScraping Summary:")
        print(f"Total incidents processed: {total}")
        print(f"New incidents stored: {new}")
        print(f"Database path: {args.db_path}")
        print(f"From date: {from_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"Request delay: {args.delay} seconds")
        
    except ValueError as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: An unexpected error occurred: {str(e)}", file=sys.stderr)
        if args.debug:
            raise
        sys.exit(1)

if __name__ == "__main__":
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Initialize scraper
    scraper = P2000Scraper()
    
    # Get incidents from the last hour
    from_date = datetime.now() - timedelta(hours=1)
    total_incidents, new_incidents = scraper.scrape_until_date(from_date)
    
    logging.info(f"Scraping complete. Found {total_incidents} incidents, {new_incidents} new.") 