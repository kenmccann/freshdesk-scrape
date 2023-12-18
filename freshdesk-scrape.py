import requests
import json
import argparse
from datetime import datetime

parser = argparse.ArgumentParser(description='Tool for gathering and saving information from a Freshdesk instance.')
parser.add_argument('-k', '--key', help='Freshdesk API key', default='', required=True)
parser.add_argument('-d', '--domain', help='Specify the Freshdesk domain (ie <domain>.freshdesk.com)', required=True)
parser.add_argument('-a', '--all', help='Specify if all tickets should be returned (potentially expensive)', required=False, action='store_true')
parser.add_argument('-r', '--range', help='Specify a range of tickets to be retrieved', type=int, nargs=2)
args = parser.parse_args()

# Your Freshdesk domain and API key
domain = args.domain
api_key = args.key

# Basic Authentication
auth = (api_key, 'X')

# Function to fetch tickets
def fetch_tickets():
    url = f'https://{domain}.freshdesk.com/api/v2/tickets'
    response = requests.get(url, auth=auth)
    return response.json()

# Function to fetch conversations for a specific ticket
def fetch_conversations(ticket_id):
    url = f'https://{domain}.freshdesk.com/api/v2/tickets/{ticket_id}/conversations'
    response = requests.get(url, auth=auth)

    # Checking the rate limit headers
    rate_limit_total = response.headers.get('X-Ratelimit-Total')
    rate_limit_remaining = response.headers.get('X-Ratelimit-Remaining')
    rate_limit_used_current = response.headers.get('X-Ratelimit-Used-Currentrequest')

    print(f"Total Rate Limit: {rate_limit_total}")
    print(f"Remaining Rate Limit: {rate_limit_remaining}")
    print(f"Rate Limit Used in Current Request: {rate_limit_used_current}")

    return response.json()

def fetch_ticket_range(int1, int2):
    ticket_range_data = []
    if int1 <= int2:
        for ticket_id in range(int1, int2 + 1):
            try:
                conversations = fetch_conversations(ticket_id)
                ticket_range_data.append({
                    'ticket_id': ticket_id,
                    'conversations': conversations
                })
            except requests.exceptions.RequestException as e:
                print(f"Error fetching data for ticket ID {ticket_id}: {e}")
    else:
        print("Invalid range: int1 should be less than or equal to int2")
    return ticket_range_data

        

# Main execution
all_conversations = []
if args.all:
  tickets = fetch_tickets()

  for ticket in tickets:
      ticket_id = ticket['id']
      conversations = fetch_conversations(ticket_id)
      all_conversations.append({
          'ticket_id': ticket_id,
          'conversations': conversations
      })
elif args.range:
    print(f"Gathering ticket range: {args.range[0]} - {args.range[1]}" )
    all_conversations = fetch_ticket_range(args.range[0], args.range[1])

# Get the current date and time
current_time = datetime.now()

# Format the date and time into a string suitable for a filename
# Example format: '20231213-151230' for 'YYYYMMDD-HHMMSS'
timestamp = current_time.strftime("%Y%m%d-%H%M%S")

# Create a unique filename using the timestamp
filename = f"freshdesk_conversations_{timestamp}.json"


# Save to a JSON file
with open(filename, 'w') as file:
    json.dump(all_conversations, file)
