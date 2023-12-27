import json
import argparse
import random
import unicodedata
import re
from transformers import GPT2Tokenizer

def normalize_text(text):
    """
    Normalize the text by converting Unicode characters to their ASCII equivalents,
    removing newline characters, unnecessary whitespaces, and a specific footer.
    """
    # Regex pattern for footer (adjust the pattern to match possible variations)
    footer_pattern = r"Want to elevate your Aqua System Knowledge\?.*Aquademy"

    # Remove the footer using regex
    text = re.sub(footer_pattern, '', text, flags=re.DOTALL)

    # Normalize Unicode characters to ASCII
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

    # Replace newline characters with a space
    text = text.replace('\n', ' ').replace('\r', ' ')

    # Replace multiple spaces with a single space
    text = ' '.join(text.split())

    return text

def format_initial_context_to_jsonl(ticket_id, subject, description):
    """
    Format the initial context (ticket_id, subject, description) into a JSONL line.
    """
    context = f"Ticket ID: {ticket_id} Subject: {normalize_text(subject)} Description: {normalize_text(description)}"
    return context

def format_conversation_entry_to_jsonl(ticket_id, conversation):
    """
    Format a single conversation entry into a JSONL line with the ticket_id.
    """
    persona = conversation['persona']
    body = normalize_text(conversation['body'])
    full_text = f"Ticket ID: {ticket_id} {persona}: {body}"
    return full_text


def split_data(tickets, split_ratio=0.8):
    """
    Split the data into training and validation sets.
    """
    random.shuffle(tickets)
    split_index = int(len(tickets) * split_ratio)
    return tickets[:split_index], tickets[split_index:]

def tokenize_and_count(text, tokenizer):
    """
    Tokenize the text and return the count of tokens.
    """
    tokens = tokenizer.tokenize(text)
    return len(tokens)

def process_tickets(input_file, split_ratio=0.8):
    """
    Process a list of tickets from the input file, save the initial context and each conversation entry as separate JSONL lines, 
    and calculate token count statistics.
    """
    tokenizer = GPT2Tokenizer.from_pretrained('gpt2')

    with open(input_file, 'r', encoding='utf-8') as file:
        tickets = json.load(file)

    training_tickets, validation_tickets = split_data(tickets, split_ratio)
    training_token_counts = []
    validation_token_counts = []

    with open('training_data.jsonl', 'w', encoding='utf-8') as train_file, open('validation_data.jsonl', 'w', encoding='utf-8') as valid_file:
        for ticket in training_tickets:
            initial_context = format_initial_context_to_jsonl(ticket['ticket_id'], ticket['subject'], ticket['description'])
            train_file.write(json.dumps({"text": initial_context}) + '\n')
            token_count = tokenize_and_count(initial_context, tokenizer)
            training_token_counts.append(token_count)
            for conversation in ticket['conversations']:
                jsonl_line = format_conversation_entry_to_jsonl(ticket['ticket_id'], conversation)
                train_file.write(json.dumps({"text": jsonl_line}) + '\n')
                token_count = tokenize_and_count(jsonl_line, tokenizer)
                training_token_counts.append(token_count)

        for ticket in validation_tickets:
            initial_context = format_initial_context_to_jsonl(ticket['ticket_id'], ticket['subject'], ticket['description'])
            valid_file.write(json.dumps({"text": initial_context}) + '\n')
            token_count = tokenize_and_count(initial_context, tokenizer)
            validation_token_counts.append(token_count)
            for conversation in ticket['conversations']:
                jsonl_line = format_conversation_entry_to_jsonl(ticket['ticket_id'], conversation)
                valid_file.write(json.dumps({"text": jsonl_line}) + '\n')
                token_count = tokenize_and_count(jsonl_line, tokenizer)
                validation_token_counts.append(token_count)

    # Function to calculate and display statistics
    def display_stats(token_counts, dataset_name):
        min_tokens = min(token_counts)
        max_tokens = max(token_counts)
        avg_tokens = sum(token_counts) / len(token_counts)
        print(f"{dataset_name} - Min Tokens: {min_tokens}, Max Tokens: {max_tokens}, Average Tokens: {avg_tokens}")

    print("Token Count Statistics:")
    display_stats(training_token_counts, "Training Set")
    display_stats(validation_token_counts, "Validation Set")

def main():
    parser = argparse.ArgumentParser(description="Format ticket data into JSONL format for model training.")
    parser.add_argument('input_file', type=str, help="The JSON file containing the ticket data")
    args = parser.parse_args()

    process_tickets(args.input_file)

if __name__ == "__main__":
    main()
