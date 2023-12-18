import requests
import json
import argparse
from datetime import datetime
import time

parser = argparse.ArgumentParser(description='Tool for gathering and saving information from a Freshdesk instance.')
parser.add_argument('-k', '--key', help='Freshdesk API key', default='', required=True)
parser.add_argument('-d', '--domain', help='Specify the Freshdesk domain (ie <domain>.freshdesk.com)', required=True)
parser.add_argument('-a', '--all', help='Specify if all tickets should be returned (potentially expensive)', required=False, action='store_true')
parser.add_argument('-r', '--range', help='Specify a range of tickets to be retrieved', type=int, nargs=2)
parser.add_argument('-l', '--limit', help='Rate limit threshold to pause script execution', type=int, default=1500)
parser.add_argument('-p', '--pause', help='Pause duration in seconds when rate limit is close', type=int, default=300)  # 300 seconds = 5 minutes

args = parser.parse_args()

# Your Freshdesk domain and API key
domain = args.domain
api_key = args.key

# Basic Authentication
auth = (api_key, 'X')

# Rate limit handling
def check_rate_limit(rate_limit_remaining, rate_limit_total, pause_duration):
    if int(rate_limit_remaining) <= args.limit:
        print("Approaching rate limit. Pausing execution...")
        while True:
            time.sleep(pause_duration)  # Pause for the specified duration

            # Dummy request to check rate limit status
            response = requests.get(f'https://{domain}.freshdesk.com/api/v2/tickets', auth=auth)
            new_remaining = int(response.headers.get('X-Ratelimit-Remaining', 0))
            new_total = int(response.headers.get('X-Ratelimit-Total', 1))

            if new_remaining >= 0.9 * new_total:  # Check if the rate limit has reset to within 90% of the total
                print("Resuming execution...")
                break
            else:
                print(f"Waiting for rate limit to reset. Current remaining: {new_remaining}")

# Function to fetch tickets
def fetch_tickets():
    tickets = []
    page = 1
    while True:
        url = f'https://{domain}.freshdesk.com/api/v2/tickets?page={page}'
        response = requests.get(url, auth=auth)

        # Checking the rate limit headers
        rate_limit_remaining = response.headers.get('X-Ratelimit-Remaining', '0')
        rate_limit_total = response.headers.get('X-Ratelimit-Total', '1')

        # Call the rate limit check function
        check_rate_limit(rate_limit_remaining, rate_limit_total, args.pause)

        data = response.json()
        if data:
            tickets.extend(data)
            page += 1
        else:
            break
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

        print(f"Total Rate Limit: {rate_limit_total}")
        print(f"Remaining Rate Limit: {rate_limit_remaining}")
        print(f"Rate Limit Used in Current Request: {rate_limit_used_current}")

        data = response.json()
        if data:
            conversations.extend(data)
            page += 1
        else:
            break
    return conversations


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
    # Confirmation message
    print(f"Data successfully saved to {filename}")