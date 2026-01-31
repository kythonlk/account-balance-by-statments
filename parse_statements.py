import os
import re
import json
import argparse
import subprocess
from datetime import datetime

# Define the structure of a transaction
class Transaction:
    def __init__(self, posting_date, value_date, description, ref_no, debit, credit, balance, source_file):
        self.posting_date = posting_date
        self.value_date = value_date
        self.description = description
        self.ref_no = ref_no
        self.debit = debit
        self.credit = credit
        self.balance = balance
        self.source_file = source_file

    def to_dict(self):
        return {
            "posting_date": self.posting_date,
            "value_date": self.value_date,
            "description": self.description,
            "ref_no": self.ref_no,
            "debit": self.debit,
            "credit": self.credit,
            "balance": self.balance,
            "source_file": self.source_file
        }

    def unique_key(self):
        # Create a unique key for deduplication
        return f"{self.posting_date}|{self.description}|{self.ref_no}|{self.debit}|{self.credit}|{self.balance}"

def parse_amount(amount_str):
    if not amount_str:
        return 0.0
    try:
        return float(amount_str.replace(',', '').strip())
    except ValueError:
        return 0.0

def parse_pdf_content(file_path):
    # Use pdftotext to extract text while maintaining layout
    try:
        result = subprocess.run(['pdftotext', '-layout', file_path, '-'], capture_output=True, text=True, check=True)
        content = result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error reading {file_path}: {e}")
        return []

    lines = content.split('\n')
    transactions = []
    
    # Regex for DD/MM/YYYY date format
    date_regex = re.compile(r'^\d{2}/\d{2}/\d{4}')
    
    current_txn = None
    
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue
            
        parts = stripped_line.split()
        
        # heuristic: A transaction line starts with a date
        if date_regex.match(parts[0]):
            # If we were building a transaction, save it
            if current_txn:
                transactions.append(current_txn)
                current_txn = None
            
            # Start parsing new transaction
            # Based on the user's PDF layout:
            # Date | Date | Description | Ref | Debit | Credit | Balance
            # But columns are fixed width relative to layout usually.
            # Let's try token based first, falling back to layout if needed.
            
            # Typical line:
            # 29/01/2026 29/01/2026 CREDIT CARD PAYMNT 30668394590 2500 0.00 9565.5
            
            # We know the last 3-4 tokens are usually numbers (Balance, Credit, Debit, Ref)
            # If the last 3 look like numbers:
            
            try:
                # Check for at least dates and some numbers
                if len(parts) >= 6:
                    posting_date = parts[0]
                    value_date = parts[1]
                    
                    # Work backwards for amounts
                    balance_str = parts[-1]
                    credit_str = parts[-2]
                    debit_str = parts[-3]
                    
                    # Ref is usually before Debit. 
                    # Sometimes Ref is merged with Description or missing? 
                    # In the sample: "30668394590" is the ref.
                    ref_str = parts[-4]
                    
                    # Everything else is description
                    # Description is from index 2 to index -4
                    description_parts = parts[2:-4]
                    description = " ".join(description_parts)
                    
                    # Validate dates to be sure
                    if date_regex.match(posting_date) and date_regex.match(value_date):
                         current_txn = Transaction(
                            posting_date, 
                            value_date, 
                            description, 
                            ref_str, 
                            parse_amount(debit_str), 
                            parse_amount(credit_str), 
                            parse_amount(balance_str),
                            os.path.basename(file_path)
                        )
            except Exception:
                # If parsing fails, skip or log
                pass
                
        elif current_txn:
            # Append continuation lines (like time or extra desc) to description
            # "14:14:55 XXXXXXXXXXXX4273"
            # Ignore purely time lines if you want, but appending is safer to keep info.
            current_txn.description += " " + stripped_line

    # Don't forget the last one
    if current_txn:
        transactions.append(current_txn)
        
    return transactions

def main():
    parser = argparse.ArgumentParser(description='Convert Bank Statement PDFs to JSON')
    parser.add_argument('input_dir', help='Directory containing PDF files')
    parser.add_argument('--output', '-o', default='transactions.json', help='Output JSON file path')
    
    args = parser.parse_args()
    
    all_transactions = []
    
    if not os.path.exists(args.input_dir):
        print(f"Directory not found: {args.input_dir}")
        return

    files = [f for f in os.listdir(args.input_dir) if f.lower().endswith('.pdf')]
    print(f"Found {len(files)} PDF files.")

    for f in files:
        path = os.path.join(args.input_dir, f)
        print(f"Processing {f}...")
        txns = parse_pdf_content(path)
        all_transactions.extend(txns)
        print(f"  Found {len(txns)} transactions.")

    # Deduplicate
    unique_txns = {}
    for txn in all_transactions:
        key = txn.unique_key()
        if key not in unique_txns:
            unique_txns[key] = txn
    
    final_list = list(unique_txns.values())
    
    # Sort by date (descending)
    def parse_date_sort(t):
        try:
            return datetime.strptime(t.posting_date, "%d/%m/%Y")
        except:
            return datetime.min

    final_list.sort(key=parse_date_sort, reverse=True)
    
    output_data = [t.to_dict() for t in final_list]
    
    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)
        
    print(f"\nSuccess! Combined {len(final_list)} unique transactions into {args.output}")

if __name__ == "__main__":
    main()
