import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import csv
import re
import json
import hashlib
from datetime import datetime
import os
from dateutil import parser as date_parser
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("groundwork_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GroundworkScraper:
    def __init__(self, trust_sites, max_depth=2):
        # Initialize trust info
        self.trust_info = {
            "https://www.groundworkatlanta.org/": {"abbrev": "ATL", "name": "Atlanta"},
            "https://www.groundworkbridgeport.org/": {"abbrev": "BPRT", "name": "Bridgeport"},
            "https://gwbuffalo.org/": {"abbrev": "BUF", "name": "Buffalo"},
            "https://groundworkcolorado.org/": {"abbrev": "DCO", "name": "Denver"},
            "https://groundworkelizabeth.org/": {"abbrev": "ENJ", "name": "Elizabeth"},
            "https://www.groundworkerie.org/": {"abbrev": "ERI", "name": "Erie"},
            "https://www.groundworkhv.org/": {"abbrev": "HV", "name": "Hudson Valley"},
            "https://www.groundworkindy.org/": {"abbrev": "IND", "name": "Indy"},
            "https://www.groundworkjacksonville.org/": {"abbrev": "JAX", "name": "Jacksonville"},
            "https://groundworklawrence.org/": {"abbrev": "LMA", "name": "Lawrence"},
            "https://www.groundworkmke.org/": {"abbrev": "MKE", "name": "Milwaukee"},
            "https://www.groundworkmobile.org/": {"abbrev": "MOB", "name": "Mobile"},
            "https://groundwork-neworleans.org/": {"abbrev": "NOLA", "name": "New Orleans"},
            "https://www.northeastkck.org/": {"abbrev": "NRG", "name": "Northeast Revitalization Group"},
            "https://www.groundworkorv.org/": {"abbrev": "ORV", "name": "Ohio River Valley"},
            "https://groundworkri.org/": {"abbrev": "RI", "name": "Rhode Island"},
            "https://www.groundworkrichmond.org/": {"abbrev": "RCA", "name": "Richmond"},
            "https://www.groundworkrva.org/": {"abbrev": "RVA", "name": "RVA"},
            "https://groundworksandiego.org/": {"abbrev": "SD", "name": "San Diego"},
            "https://groundworksomerville.org/": {"abbrev": "SOM", "name": "Somerville"},
            "https://groundworksouthcoast.org/": {"abbrev": "SC", "name": "Southcoast"}
        }
        
        self.trust_sites = [site.strip() for site in trust_sites if site.strip()]
        self.max_depth = max_depth
        self.current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create directory for results if it doesn't exist
        self.results_dir = "scraper_results"
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
        
        # Keywords to identify event content
        self.event_keywords = [
            'event', 'events', 'workshop', 'webinar', 'conference', 'seminar', 
            'meeting', 'meetup', 'calendar', 'upcoming', 'schedule',
            'register', 'registration', 'attend', 'join us'
        ]
        
        # Common page patterns for events
        self.event_page_patterns = [
            '/event', '/events', '/calendar', '/upcoming', '/schedule', 
            '/workshop', '/webinar'
        ]
        
        # Initialize hash sets for deduplication
        self.event_hashes = set()
        
        # Special filters for specific sites
        self.colorado_filters = [
            '0 events', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat',
            'events,', 'event search'
        ]

    def generate_hash(self, item):
        """Generate a hash for deduplication"""
        # Create a string with key identifying information
        if 'title' in item:
            key_str = f"{item.get('title', '')}-{item.get('date', '')}-{item.get('source_url', '')}"
            return hashlib.md5(key_str.encode('utf-8')).hexdigest()
        return None

    def is_likely_event_page(self, url, soup):
        """Determine if a page is likely an events page"""
        url_lower = url.lower()
        
        # Check URL patterns
        if any(pattern in url_lower for pattern in self.event_page_patterns):
            return True
            
        # Check page title
        title_tag = soup.find('title')
        if title_tag and any(keyword in title_tag.get_text().lower() for keyword in self.event_keywords):
            return True
            
        # Check headings
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            if any(keyword in heading.get_text().lower() for keyword in self.event_keywords):
                return True
                
        return False

    def extract_date_and_time(self, text):
        """Extract date and time from text, return as tuple (date, time)"""
        if not text:
            return None, None
            
        # Clean up text
        text = re.sub(r'\s+', ' ', text)
        
        # Try to extract with dateutil parser first
        try:
            dt = date_parser.parse(text, fuzzy=True)
            date_str = dt.strftime("%Y-%m-%d")
            
            # Check if time information is available
            if dt.hour != 0 or dt.minute != 0:
                time_str = dt.strftime("%H:%M")
            else:
                # Try to find time pattern in text
                time_match = re.search(r'(\d{1,2}):(\d{2})(?:\s*(am|pm|AM|PM))?', text)
                time_str = None
                if time_match:
                    hour, minute, ampm = time_match.groups()
                    if ampm and ampm.lower() == 'pm' and int(hour) < 12:
                        hour = str(int(hour) + 12)
                    time_str = f"{hour.zfill(2)}:{minute}"
                
            return date_str, time_str
        except:
            pass
            
        # Try common date formats with regex
        # Format: MM/DD/YYYY
        date_match = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](20\d{2})', text)
        if date_match:
            month, day, year = date_match.groups()
            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Look for time
            time_match = re.search(r'(\d{1,2}):(\d{2})(?:\s*(am|pm|AM|PM))?', text)
            time_str = None
            if time_match:
                hour, minute, ampm = time_match.groups()
                if ampm and ampm.lower() == 'pm' and int(hour) < 12:
                    hour = str(int(hour) + 12)
                time_str = f"{hour.zfill(2)}:{minute}"
                
            return date_str, time_str
            
        # Format: Month Day, Year
        months = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        
        date_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})', text, re.IGNORECASE)
        if date_match:
            month, day, year = date_match.groups()
            date_str = f"{year}-{months[month.lower()]}-{day.zfill(2)}"
            
            # Look for time
            time_match = re.search(r'(\d{1,2}):(\d{2})(?:\s*(am|pm|AM|PM))?', text)
            time_str = None
            if time_match:
                hour, minute, ampm = time_match.groups()
                if ampm and ampm.lower() == 'pm' and int(hour) < 12:
                    hour = str(int(hour) + 12)
                time_str = f"{hour.zfill(2)}:{minute}"
                
            return date_str, time_str
            
        return None, None

    def extract_location(self, text):
        """Enhanced location extraction with multiple strategies"""
        if not text:
            return None
            
        # Look for location patterns
        location_indicators = [
            'at ', 'location:', 'venue:', 'where:', 'address:'
        ]
        
        lower_text = text.lower()
        
        for indicator in location_indicators:
            idx = lower_text.find(indicator)
            if idx >= 0:
                # Extract text after the indicator
                location_text = text[idx + len(indicator):].strip()
                
                # Try to get a reasonable chunk (until punctuation or new line)
                match = re.search(r'^([^\.!?\n]+)', location_text)
                if match:
                    return match.group(1).strip()
                    
        # Look for address patterns
        address_match = re.search(r'\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)(?:[,\s]+[A-Za-z\s]+(?:,\s*[A-Z]{2})?)?', text)
        if address_match:
            return address_match.group(0).strip()
            
        return None

    def extract_event_details(self, url, soup):
        """Extract event details from a page with improved extraction"""
        events = []
        site_domain = urllib.parse.urlparse(url).netloc.lower()
        
        # First try to identify dedicated event containers
        event_containers = []
        
        # 1. Look for specific event listing structures
        for container in soup.find_all(['div', 'article', 'section', 'li']):
            # Get class and id attributes
            classes = container.get('class', [])
            class_str = ' '.join(classes) if isinstance(classes, list) else str(classes)
            id_str = container.get('id', '')
            
            # Check for event-related indicators
            if (any(keyword in class_str.lower() for keyword in self.event_keywords) or 
                any(keyword in id_str.lower() for keyword in self.event_keywords)):
                event_containers.append(container)
                
        # 2. Process identified event containers
        if event_containers:
            for container in event_containers:
                events.extend(self._process_event_container(container, url))
        
        # 3. Fallback methods if few or no events found through containers
        if len(events) < 3:
            # Try to find events from structured data
            structured_events = self._extract_events_from_structured_data(soup, url)
            events.extend(structured_events)
            
            # Try to identify events from page structure
            if len(events) < 3:
                structure_events = self._extract_events_from_page_structure(soup, url)
                events.extend(structure_events)
                
        # Apply special filtering for Colorado calendar UI
        if "groundworkcolorado.org" in site_domain:
            filtered_events = []
            for event in events:
                # Skip calendar UI elements
                if event.get('title') and any(filter_str in event['title'].lower() for filter_str in self.colorado_filters):
                    continue
                
                # Skip very short titles or single numbers
                if not event.get('title') or len(event['title']) < 3 or event['title'].strip().isdigit():
                    continue
                    
                filtered_events.append(event)
            return filtered_events
            
        return events
    
    def _process_event_container(self, container, page_url):
        """Process a container that might hold one or more events"""
        events = []
        
        # Handle different container types
        if container.name == 'li':
            # This could be a single event in a list
            event = self._extract_single_event(container, page_url)
            if event:
                events.append(event)
        else:
            # This might be a container with multiple events or a single detailed event
            
            # Check if there are sub-containers that might be individual events
            sub_events = container.find_all(['div', 'article', 'li'], class_=lambda c: c and any(
                keyword in str(c).lower() for keyword in ['event', 'item', 'card', 'entry']))
                
            if sub_events:
                for sub_event in sub_events:
                    event = self._extract_single_event(sub_event, page_url)
                    if event:
                        events.append(event)
            else:
                # Try to extract as a single event
                event = self._extract_single_event(container, page_url)
                if event:
                    events.append(event)
                    
        return events
        
    def _extract_single_event(self, elem, page_url):
        """Extract details from what appears to be a single event element"""
        # Initialize default event structure
        event = {
            'title': None,
            'date': None,
            'time': None,
            'description': None,
            'location': None,
            'url': None,
            'source_url': page_url
        }
        
        # 1. Extract title
        # Look for the most prominent title element
        title_candidates = []
        
        # Check headings
        for heading in elem.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
            title_candidates.append((heading.get_text().strip(), 5 - int(heading.name[1])))
            
        # Check strong/b elements
        for strong in elem.find_all(['strong', 'b']):
            if len(strong.get_text().strip()) > 10:  # Avoid very short text
                title_candidates.append((strong.get_text().strip(), 1))
                
        # Check elements with title-like classes
        for title_elem in elem.find_all(class_=lambda c: c and any(word in str(c).lower() for word in ['title', 'name', 'headline'])):
            title_candidates.append((title_elem.get_text().strip(), 3))
            
        # Select the best title based on priority
        if title_candidates:
            title_candidates.sort(key=lambda x: x[1], reverse=True)
            event['title'] = title_candidates[0][0]
        
        # 2. Extract date and time information
        date_elements = []
        
        # Check elements with date-related classes or text
        for date_elem in elem.find_all(class_=lambda c: c and any(word in str(c).lower() for word in ['date', 'time', 'when'])):
            date_elements.append(date_elem.get_text().strip())
            
        # Check elements with date-related text
        for p_elem in elem.find_all(['p', 'div', 'span']):
            text = p_elem.get_text().strip().lower()
            if any(marker in text for marker in ['date:', 'when:', 'time:']):
                date_elements.append(p_elem.get_text().strip())
                
        # Try to extract date from available elements
        for date_text in date_elements:
            date_str, time_str = self.extract_date_and_time(date_text)
            if date_str:
                event['date'] = date_str
                if time_str:
                    event['time'] = time_str
                break
                
        # If no date found, try extracting from the entire element text
        if not event['date']:
            date_str, time_str = self.extract_date_and_time(elem.get_text())
            if date_str:
                event['date'] = date_str
                if time_str:
                    event['time'] = time_str
        
        # 3. Extract location
        location_elements = []
        
        # Check elements with location-related classes
        for loc_elem in elem.find_all(class_=lambda c: c and any(word in str(c).lower() for word in ['location', 'venue', 'place', 'where'])):
            location_elements.append(loc_elem.get_text().strip())
            
        # Check elements with location-related text
        for p_elem in elem.find_all(['p', 'div', 'span']):
            text = p_elem.get_text().strip().lower()
            if any(marker in text for marker in ['location:', 'venue:', 'place:', 'where:']):
                location_elements.append(p_elem.get_text().strip())
                
        # Try to extract location from available elements
        for loc_text in location_elements:
            location = self.extract_location(loc_text)
            if location:
                event['location'] = location
                break
                
        # If no location found, try extracting from the entire element text
        if not event['location']:
            location = self.extract_location(elem.get_text())
            if location:
                event['location'] = location
        
        # 4. Extract description
        desc_candidates = []
        
        # Check paragraphs that are not the title
        for p in elem.find_all('p'):
            p_text = p.get_text().strip()
            if p_text and p_text != event['title'] and len(p_text) > 20:
                desc_candidates.append(p_text)
                
        # Check div elements with description-like classes
        for desc_elem in elem.find_all(class_=lambda c: c and any(word in str(c).lower() for word in ['desc', 'content', 'text', 'detail'])):
            desc_text = desc_elem.get_text().strip()
            if desc_text and desc_text != event['title'] and len(desc_text) > 20:
                desc_candidates.append(desc_text)
                
        # Select the best description
        if desc_candidates:
            # Sort by length, prefer longer descriptions
            desc_candidates.sort(key=len, reverse=True)
            event['description'] = desc_candidates[0]
        
        # 5. Extract URL
        link = None
        
        # Check if the element itself is an anchor or has a single prominent anchor
        if elem.name == 'a':
            link = elem
        else:
            # Check for anchors containing the title text
            if event['title']:
                for a in elem.find_all('a'):
                    if event['title'] in a.get_text().strip():
                        link = a
                        break
                        
            # If no link found with title, look for other prominent links
            if not link:
                for a in elem.find_all('a'):
                    if 'more' in a.get_text().lower() or 'details' in a.get_text().lower() or a.find('img'):
                        link = a
                        break
                        
            # Last resort: just take the first link
            if not link and elem.find('a'):
                link = elem.find('a')
                
        if link and link.get('href'):
            event['url'] = urllib.parse.urljoin(page_url, link.get('href'))
            
        # Only return the event if we have at least a title
        if event['title'] and len(event['title']) > 3:
            return event
            
        return None

    def _extract_events_from_structured_data(self, soup, page_url):
        """Try to extract events from JSON-LD or microdata"""
        events = []
        
        # Check for JSON-LD structured data
        for script in soup.find_all('script', {'type': 'application/ld+json'}):
            try:
                data = json.loads(script.string)
                
                # Handle single event
                if isinstance(data, dict) and data.get('@type') == 'Event':
                    event = self._process_structured_event(data, page_url)
                    if event:
                        events.append(event)
                
                # Handle multiple events
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Event':
                            event = self._process_structured_event(item, page_url)
                            if event:
                                events.append(event)
                                
                # Handle @graph format
                elif isinstance(data, dict) and '@graph' in data:
                    for item in data['@graph']:
                        if isinstance(item, dict) and item.get('@type') == 'Event':
                            event = self._process_structured_event(item, page_url)
                            if event:
                                events.append(event)
            except:
                continue
                
        return events
        
    def _process_structured_event(self, data, page_url):
        """Process a structured data event"""
        event = {
            'title': None,
            'date': None,
            'time': None,
            'description': None,
            'location': None,
            'url': None,
            'source_url': page_url
        }
        
        # Extract title
        if 'name' in data:
            event['title'] = data['name']
            
        # Extract date & time
        if 'startDate' in data:
            try:
                dt = date_parser.parse(data['startDate'])
                event['date'] = dt.strftime("%Y-%m-%d")
                if dt.hour != 0 or dt.minute != 0:
                    event['time'] = dt.strftime("%H:%M")
            except:
                pass
                
        # Extract description
        if 'description' in data:
            event['description'] = data['description']
            
        # Extract location
        if 'location' in data:
            if isinstance(data['location'], dict):
                if 'name' in data['location']:
                    event['location'] = data['location']['name']
                elif 'address' in data['location']:
                    if isinstance(data['location']['address'], dict):
                        address_parts = []
                        for field in ['streetAddress', 'addressLocality', 'addressRegion', 'postalCode']:
                            if field in data['location']['address']:
                                address_parts.append(str(data['location']['address'][field]))
                        event['location'] = ' '.join(address_parts)
                    else:
                        event['location'] = str(data['location']['address'])
            else:
                event['location'] = str(data['location'])
                
        # Extract URL
        if 'url' in data:
            event['url'] = urllib.parse.urljoin(page_url, data['url'])
            
        # Only return if we have at least a title
        if event['title']:
            return event
            
        return None

    def _extract_events_from_page_structure(self, soup, page_url):
        """Extract events based on page structure patterns"""
        events = []
        
        # Look for event-like heading + content patterns
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
        for heading in headings:
            heading_text = heading.get_text().strip()
            
            # Skip very short or navigation-like headings
            if len(heading_text) < 5 or heading_text.lower() in ['menu', 'navigation', 'main menu']:
                continue
                
            # Look for a date pattern in the heading text
            date_str, time_str = self.extract_date_and_time(heading_text)
            
            # Get content following the heading
            next_elems = []
            next_elem = heading.find_next_sibling()
            
            # Gather the next few elements
            while next_elem and len(next_elems) < 3:
                if next_elem.name in ['p', 'div'] and len(next_elem.get_text().strip()) > 20:
                    next_elems.append(next_elem)
                next_elem = next_elem.find_next_sibling()
                
            # If we have content and either a date in the heading or date-like text in the content
            if next_elems:
                combined_content = ' '.join([e.get_text().strip() for e in next_elems])
                
                # If no date found in heading, try to find it in content
                if not date_str:
                    date_str, time_str = self.extract_date_and_time(combined_content)
                    
                # Extract location
                location = self.extract_location(combined_content)
                
                # Only create an event if we have a date or the heading is event-like
                if date_str or any(keyword in heading_text.lower() for keyword in self.event_keywords):
                    # Get URL from heading or content
                    url = None
                    link = heading.find('a')
                    if not link and next_elems[0].find('a'):
                        link = next_elems[0].find('a')
                    if link and link.get('href'):
                        url = urllib.parse.urljoin(page_url, link.get('href'))
                        
                    events.append({
                        'title': heading_text,
                        'date': date_str,
                        'time': time_str,
                        'description': combined_content[:300] + ('...' if len(combined_content) > 300 else ''),
                        'location': location,
                        'url': url,
                        'source_url': page_url
                    })
                    
        return events

    def find_events(self):
        """Find events across all Groundwork Trust websites"""
        print("\nSearching for Events across Groundwork Trust websites...")
        logger.info("Starting search for events across Groundwork Trust websites")
        start_time = time.time()
        
        # Store results
        event_findings = []
        pages_visited = 0
        
        # Reset hash sets for deduplication
        self.event_hashes = set()
        
        for trust_site in self.trust_sites:
            logger.info(f"Examining: {trust_site}")
            print(f"\nExamining: {trust_site}")
            
            # Get trust info
            trust_info = self.trust_info.get(trust_site, {"abbrev": "UNK", "name": "Unknown"})
            trust_abbrev = trust_info["abbrev"]
            trust_name = trust_info["name"]
            
            visited_urls = set()
            
            def crawl_page(url, depth=0):
                nonlocal pages_visited
                if depth >= self.max_depth or url in visited_urls:
                    return
                
                visited_urls.add(url)
                pages_visited += 1
                
                print(f"\rDepth: {depth}, Pages visited: {pages_visited}, Checking: {url[:50]}...", end="")
                
                try:
                    # Add random delay to be respectful
                    time.sleep(1 + (hash(url) % 2))
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml',
                        'Accept-Language': 'en-US,en;q=0.9'
                    }
                    
                    response = requests.get(url, headers=headers, timeout=15)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Check if this is an event page
                    if self.is_likely_event_page(url, soup):
                        logger.info(f"Found likely event page: {url}")
                        events = self.extract_event_details(url, soup)
                        for event in events:
                            # Create hash for deduplication
                            event_hash = self.generate_hash(event)
                            
                            # Skip if we've seen this event before
                            if event_hash and event_hash in self.event_hashes:
                                continue
                                
                            # Add to hash set
                            if event_hash:
                                self.event_hashes.add(event_hash)
                            
                            event_findings.append({
                                'trust_site': trust_site,
                                'trust_abbrev': trust_abbrev,
                                'trust_name': trust_name,
                                'page_url': url,
                                'title': event.get('title'),
                                'date': event.get('date'),
                                'time': event.get('time'),
                                'description': event.get('description'),
                                'location': event.get('location'),
                                'event_url': event.get('url')
                            })
                        print(f"\nFound {len(events)} events on {url}")
                        logger.info(f"Found {len(events)} events on {url}")
                    
                    # Also check non-event pages for event information
                    elif depth < 1:  # Only on first level pages
                        events = self.extract_event_details(url, soup)
                        if events:
                            for event in events:
                                # Create hash for deduplication
                                event_hash = self.generate_hash(event)
                                
                                # Skip if we've seen this event before
                                if event_hash and event_hash in self.event_hashes:
                                    continue
                                    
                                # Add to hash set
                                if event_hash:
                                    self.event_hashes.add(event_hash)
                                
                                event_findings.append({
                                    'trust_site': trust_site,
                                    'trust_abbrev': trust_abbrev,
                                    'trust_name': trust_name,
                                    'page_url': url,
                                    'title': event.get('title'),
                                    'date': event.get('date'),
                                    'time': event.get('time'),
                                    'description': event.get('description'),
                                    'location': event.get('location'),
                                    'event_url': event.get('url')
                                })
                            print(f"\nFound {len(events)} events on non-event page {url}")
                            logger.info(f"Found {len(events)} events on non-event page {url}")
                    
                    # Follow links within the same domain
                    if depth < self.max_depth:
                        for link in soup.find_all('a'):
                            href = link.get('href')
                            if href:
                                full_url = urllib.parse.urljoin(url, href)
                                
                                # Stay within the same domain and avoid common non-content links
                                if (full_url.startswith(trust_site) and 
                                    '#' not in full_url and 
                                    'javascript:' not in full_url and
                                    'mailto:' not in full_url and
                                    'tel:' not in full_url and
                                    '.pdf' not in full_url and
                                    '.jpg' not in full_url and
                                    '.png' not in full_url):
                                    
                                    # Prioritize exploring event pages first
                                    is_priority = any(pattern in full_url.lower() for pattern in 
                                                    self.event_page_patterns)
                                    
                                    if is_priority:
                                        crawl_page(full_url, depth + 1)
                                    elif len(visited_urls) < 100:  # Limit to avoid crawling too deeply
                                        crawl_page(full_url, depth + 1)
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error accessing {url}: {e}")
                    print(f"\nError accessing {url}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error on {url}: {e}")
                    print(f"\nUnexpected error on {url}: {e}")
            
            # Start crawling from the trust's homepage
            try:
                crawl_page(trust_site)
            except Exception as e:
                logger.error(f"Error processing {trust_site}: {e}")
                print(f"\nError processing {trust_site}: {e}")
        
        # Sort events by date (putting None dates last)
        current_year = datetime.now().year
        
        def get_sortable_date(event):
            if not event.get('date'):
                return f"{current_year + 10}-12-31"  # Far future date for items without dates
            return event.get('date')
            
        event_findings.sort(key=get_sortable_date)
        
        # Save results to CSV
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        events_csv_filename = os.path.join(self.results_dir, f"events_findings_{timestamp}.csv")
        
        # Save events
        with open(events_csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(['Trust Abbrev', 'Trust Name', 'Trust Website', 'Page URL', 'Event Title', 'Date', 'Time', 'Location', 'Description', 'Event URL', 'Scan Date'])
            for finding in event_findings:
                csvwriter.writerow([
                    finding.get('trust_abbrev', ''),
                    finding.get('trust_name', ''),
                    finding['trust_site'],
                    finding['page_url'],
                    finding['title'],
                    finding.get('date', ''),
                    finding.get('time', ''),
                    finding.get('location', ''),
                    finding.get('description', ''),
                    finding.get('event_url', ''),
                    self.current_date
                ])
        
        # Also save as JSON for easier programmatic access
        with open(os.path.join(self.results_dir, f"events_findings_{timestamp}.json"), 'w', encoding='utf-8') as f:
            json.dump(event_findings, f, indent=2)
        
        # Print summary
        elapsed_time = time.time() - start_time
        print("\n\n=== SEARCH COMPLETE ===")
        print(f"Time taken: {elapsed_time:.2f} seconds")
        print(f"Pages visited: {pages_visited}")
        print(f"Total events found: {len(event_findings)}")
        print(f"Events results saved to: {events_csv_filename}")
        
        return {
            'events': event_findings
        }

# Trust sites list
trust_sites = [
    "https://www.groundworkatlanta.org/",
    "https://www.groundworkbridgeport.org/",
    "https://gwbuffalo.org/",
    "https://groundworkcolorado.org/",
    "https://groundworkelizabeth.org/",
    "https://www.groundworkerie.org/",
    "https://www.groundworkhv.org/",
    "https://www.groundworkindy.org/",
    "https://www.groundworkjacksonville.org/",
    "https://groundworklawrence.org/",
    "https://www.groundworkmke.org/",
    "https://www.groundworkmobile.org/",
    "https://groundwork-neworleans.org/",
    "https://www.northeastkck.org/",
    "https://www.groundworkorv.org/",
    "https://groundworkri.org/",
    "https://www.groundworkrichmond.org/",
    "https://www.groundworkrva.org/",
    "https://groundworksandiego.org/",
    "https://groundworksomerville.org/",
    "https://groundworksouthcoast.org/"
]

# Run the scraper
if __name__ == "__main__":
    scraper = GroundworkScraper(trust_sites, max_depth=2)
    results = scraper.find_events()