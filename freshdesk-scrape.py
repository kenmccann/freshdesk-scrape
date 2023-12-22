import requests
import json
import argparse
from datetime import datetime
import time
import sqlite3
import re
from tqdm import tqdm

parser = argparse.ArgumentParser(description='Tool for gathering and saving information from a Freshdesk instance.')
parser.add_argument('-k', '--key', help='Freshdesk API key', default='', required=True)
parser.add_argument('-d', '--domain', help='Specify the Freshdesk domain (ie <domain>.freshdesk.com)', required=True)
parser.add_argument('-a', '--all', help='Specify if all tickets should be returned (potentially expensive)', required=False, action='store_true')
parser.add_argument('-r', '--range', help='Specify a range of tickets to be retrieved', type=int, nargs=2)
parser.add_argument('-l', '--limit', help='Rate limit threshold to pause script execution', type=int, default=1500)
parser.add_argument('-p', '--pause', help='Pause duration in seconds when rate limit is close', type=int, default=300)  # 300 seconds = 5 minutes
parser.add_argument('-s', '--delay', help='Delay in seconds between API requests', type=int, default=0)
parser.add_argument('-u', '--updated_since', help='Fetch tickets updated since a specified date (format: YYYY-MM-DD)', type=str)
parser.add_argument('-D', '--debug', help='Enable debug messaging to the console output', required=False, action='store_true')
parser.add_argument('-e', '--export', help='Select this mode for exporting the ticket data', required=False, action='store_true')

args = parser.parse_args()

# Freshdesk domain and API key
domain = args.domain
api_key = args.key

# Basic Authentication
auth = (api_key, 'X')

# Rate limit handling
def check_rate_limit(rate_limit_remaining, rate_limit_total, pause_duration):
    if int(rate_limit_remaining) <= args.limit:
        tqdm.write("Approaching rate limit. Pausing execution...")
        while True:
            time.sleep(pause_duration)  # Pause for the specified duration

            # Dummy request to check rate limit status
            response = requests.get(f'https://{domain}.freshdesk.com/api/v2/tickets', auth=auth)
            new_remaining = int(response.headers.get('X-Ratelimit-Remaining', 0))
            new_total = int(response.headers.get('X-Ratelimit-Total', 1))

            if new_remaining >= 0.9 * new_total:  # Check if the rate limit has reset to within 90% of the total
                tqdm.write("Resuming execution...")
                break
            else:
                tqdm.write(f"Waiting for rate limit to reset. Current remaining: {new_remaining}")

# Function to fetch tickets
def fetch_tickets(updated_since=None):
    tickets = []
    page = 1
    max_pages = 300  # Freshdesk API limit
    while page <= max_pages:
        url = f'https://{domain}.freshdesk.com/api/v2/tickets?include=description&page={page}'
        if updated_since:
            url += f"&updated_since={updated_since}"
        response = requests.get(url, auth=auth)
        if response.status_code != 200:
            tqdm.write(f"Stopping at page {page}. Response code: {response.status_code}, Message: {response.text}")
            break

        # Checking the rate limit headers
        rate_limit_remaining = response.headers.get('X-Ratelimit-Remaining', '0')
        rate_limit_total = response.headers.get('X-Ratelimit-Total', '1')

        # Call the rate limit check function
        check_rate_limit(rate_limit_remaining, rate_limit_total, args.pause)
        # time.sleep(args.delay)

        data = response.json()
        if data:
            tickets.extend(data)
            page += 1
        else:
            break

        page += 1
    return tickets

# Function to fetch conversations for a specific ticket
def fetch_conversations(ticket_id):
    conversations = []
    page = 1
    while True:
        url = f'https://{domain}.freshdesk.com/api/v2/tickets/{ticket_id}/conversations?page={page}'
        response = requests.get(url, auth=auth)

        # Existing rate limit header retrieval
        rate_limit_remaining = response.headers.get('X-Ratelimit-Remaining', '0')
        rate_limit_total = response.headers.get('X-Ratelimit-Total', '1')

        # Call the rate limit check function
        check_rate_limit(rate_limit_remaining, rate_limit_total, args.pause)

        #rate_limit_total = response.headers.get('X-Ratelimit-Total')
        #rate_limit_remaining = response.headers.get('X-Ratelimit-Remaining')
        rate_limit_used_current = response.headers.get('X-Ratelimit-Used-Currentrequest')

        if args.debug:
            tqdm.write(f"Total Rate Limit: {rate_limit_total}")
            tqdm.write(f"Remaining Rate Limit: {rate_limit_remaining}")
            tqdm.write(f"Rate Limit Used in Current Request: {rate_limit_used_current}")

        time.sleep(args.delay)

        data = response.json()
        if data:
            conversations.extend(data)
            page += 1
        else:
            break
    return conversations


def fetch_ticket_range(int1, int2, all_tickets):
    ticket_range_data = []
    if int1 <= int2:
        # Filter tickets that fall within the specified range
        valid_ticket_ids = [ticket['id'] for ticket in all_tickets if int1 <= ticket['id'] <= int2]

        for ticket_id in valid_ticket_ids:
            try:
                conversations = fetch_conversations(ticket_id)
                ticket_range_data.append({
                    'ticket_id': ticket_id,
                    'conversations': conversations
                })
            except requests.exceptions.RequestException as e:
                tqdm.write(f"Error fetching data for ticket ID {ticket_id}: {e}")
    else:
        tqdm.write("Invalid range: int1 should be less than or equal to int2")
    return ticket_range_data


def store_ticket(ticket, cursor):
    # Check if the ticket is already in the database
    cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket['id'],))
    if cursor.fetchone() is None:
        # Ticket not in database, insert it
        cursor.execute('INSERT INTO tickets (id, created_at, updated_at, subject, description, severity, region, other_ticket_info) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (ticket['id'], ticket['created_at'], ticket['updated_at'], ticket['subject'], strip_email_headers(ticket['description_text']), ticket['custom_fields']['severity'], ticket['custom_fields']['cf_ticket_region'], json.dumps(ticket)))
        return True  # Indicates the ticket was stored
    return False  # Indicates the ticket was already in the database

def store_conversation(ticket_id, conversation, cursor):
    # Check for existing conversation to avoid duplicates
    cursor.execute('SELECT * FROM conversations WHERE conversation_id = ?', (conversation['id'],))
    if cursor.fetchone() is None:
        # Conversation not in database, insert it
        isIncoming = conversation['incoming']
        isPrivate = conversation['private']
        persona = ''
        if isIncoming and not isPrivate:
            persona = 'Customer'
        elif isIncoming and isPrivate:
            persona = "Aqua Development Discussion"
        elif not isIncoming and not isPrivate:
            persona = 'Aqua Support Agent'
        elif not isIncoming and isPrivate:
            persona = 'Aqua Internal Discussion'
        else: persona = 'Unknown User'
        cursor.execute('INSERT INTO conversations (ticket_id, conversation_id, created_at, persona, body) VALUES (?, ?, ?, ?, ?)',
                       (ticket_id, conversation['id'], conversation['created_at'], persona, conversation['body_text']))


def strip_email_headers(description):
    """
    Strips email headers from the ticket description.

    Args:
    description (str): The description field of the ticket.

    Returns:
    str: The description with email headers removed.
    """
    # Regular expression to identify potential end of headers
    # This regex looks for two consecutive newline characters which often separate headers from the body
    end_of_headers_regex = r"(\r?\n){2,}"

    # Find the end of the headers using regex
    match = re.search(end_of_headers_regex, description)
    
    if match:
        # Get the index where the body starts
        start_idx = match.end()
        return description[start_idx:].strip()
    else:
        # If no pattern is found, return the original description
        return description

# Main execution
# all_conversations = []

# Create a global tqdm instance for writing messages
global_pbar = None

# Establish a connection to the SQLite database
database_file = 'tickets.db'
conn = sqlite3.connect(database_file)
cursor = conn.cursor()

# SQL to create 'tickets' table
create_tickets_table = '''
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY,
    created_at TEXT,
    updated_at TEXT,
    subject TEXT,
    description TEXT,
    severity TEXT,
    region TEXT,
    other_ticket_info TEXT
)
'''

# SQL to create 'conversations' table
create_conversations_table = '''
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    ticket_id INTEGER,
    created_at TEXT,
    persona TEXT,
    body TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
)
'''

# Execute the SQL commands to create the tables
cursor.execute(create_tickets_table)
cursor.execute(create_conversations_table)

if args.updated_since:
    print(f"Fetching tickets updated since {args.updated_since}")
    all_tickets = fetch_tickets(args.updated_since)
    global_pbar = tqdm(all_tickets, desc="Processing tickets", unit="ticket")
    for ticket in global_pbar:
        ticket_id = ticket['id']

        if store_ticket(ticket, cursor):
            if args.debug: tqdm.write(f"Stored ticket ID {ticket_id} in the database.")
        else:
            if args.debug: tqdm.write(f"Ticket ID {ticket_id} is already in the database.")
            continue # Don't attempt to store further conversations - assume they're already there

        conversations = fetch_conversations(ticket_id)
        for conversation in conversations:
            store_conversation(ticket['id'], conversation, cursor)
        # all_conversations.append({
        #     'ticket_id': ticket_id,
        #     'conversations': conversations
        # })
elif args.all:
    tickets = fetch_tickets()

    global_pbar = tqdm(tickets, desc="Processing tickets", unit="ticket")
    for ticket in global_pbar:
        ticket_id = ticket['id']

        if store_ticket(ticket, cursor):
            if args.debug: tqdm.write(f"Stored ticket ID {ticket_id} in the database.")
        else:
            if args.debug: tqdm.write(f"Ticket ID {ticket_id} is already in the database.")
            continue # Don't attempt to store further conversations - assume they're already there

        conversations = fetch_conversations(ticket_id)
        for conversation in conversations:
            store_conversation(ticket['id'], conversation, cursor)
        # all_conversations.append({
        #     'ticket_id': ticket_id,
        #     'conversations': conversations
        # })
elif args.range:
    all_tickets = fetch_tickets()
    tqdm.write(f"Gathering ticket range: {args.range[0]} - {args.range[1]}" )
    conversations = fetch_ticket_range(args.range[0], args.range[1], all_tickets)
    for conversation in conversations:
        store_conversation(conversation['ticket_id'], conversation, cursor)
    # all_conversations = conversations
elif args.export:
    tqdm.write("Exporting ticket data...")

    # Querying the database for tickets and conversations
    with sqlite3.connect(database_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tickets")
        tickets = cursor.fetchall()

        # Preparing data structure for JSON export
        tickets_data = []
        for ticket in tickets:
            ticket_id, created_at, updated_at, subject, description, severity, region, other_ticket_info = ticket
            cursor.execute("SELECT * FROM conversations WHERE ticket_id = ? ORDER BY created_at", (ticket_id,))
            conversations = cursor.fetchall()

            # Organizing conversations
            conversation_data = []
            for conversation in conversations:
                _, conversation_id, _, created_at, persona, body = conversation
                if persona in ['Aqua Development Discussion','Aqua Internal Discussion']: continue  # Focus only on Support/Customer convos
                conversation_data.append({
                    "conversation_id": conversation_id,
                    "created_at": created_at,
                    "persona": persona,
                    "body": body
                })

            # Organizing ticket data
            tickets_data.append({
                "ticket_id": ticket_id,
                "created_at": created_at,
                "updated_at": updated_at,
                "subject": subject,
                "description": description,
                "severity": severity,
                "region": region,
                "conversations": conversation_data
            })

    # Writing data to JSON file
    export_filename = f"exported_tickets_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(export_filename, 'w', encoding='utf-8') as file:
        json.dump(tickets_data, file, ensure_ascii=False, indent=4)

    tqdm.write(f"Ticket data exported to {export_filename}")

conn.commit()
conn.close()

# current_time = datetime.now()
# timestamp = current_time.strftime("%Y%m%d-%H%M%S")

# Record ticket IDs and conversations file
# record_filename = f"processed_tickets_{timestamp}.txt"
# with open(record_filename, 'w') as record_file:
#     ticket_ids = [ticket['id'] for ticket in all_tickets]
#     record_file.write(f"Conversations for tickets: {ticket_ids}\n")
#     record_file.write(f"Saved in file: {filename}\n")

tqdm.write(f"All tickets and conversations saved to {database_file}")