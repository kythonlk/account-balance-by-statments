import streamlit as st
import subprocess
import tempfile
import os
import re
import json
import pandas as pd
from datetime import datetime

# --- Parsing Logic (Adapted for Streamlit) ---

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
        return f"{self.posting_date}|{self.description}|{self.ref_no}|{self.debit}|{self.credit}|{self.balance}"

def parse_amount(amount_str):
    if not amount_str:
        return 0.0
    try:
        return float(amount_str.replace(',', '').strip())
    except ValueError:
        return 0.0

def parse_pdf_from_bytes(file_bytes, filename):
    # Write bytes to a temp file so pdftotext can read it easily
    # (pdftotext stdin support can be flaky with layout sometimes, tempfile is safer)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        result = subprocess.run(['pdftotext', '-layout', tmp_path, '-'], capture_output=True, text=True, check=True)
        content = result.stdout
    except subprocess.CalledProcessError as e:
        st.error(f"Error reading {filename}: {e}")
        return []
    finally:
        os.remove(tmp_path)

    lines = content.split('\n')
    transactions = []
    
    # Regex for DD/MM/YYYY
    date_regex = re.compile(r'^\d{2}/\d{2}/\d{4}')
    
    current_txn = None
    
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue
            
        parts = stripped_line.split()
        
        # Heuristic: A transaction line starts with a date
        if date_regex.match(parts[0]):
            if current_txn:
                transactions.append(current_txn)
                current_txn = None
            
            try:
                if len(parts) >= 6:
                    posting_date = parts[0]
                    value_date = parts[1]
                    balance_str = parts[-1]
                    credit_str = parts[-2]
                    debit_str = parts[-3]
                    ref_str = parts[-4]
                    description_parts = parts[2:-4]
                    description = " ".join(description_parts)
                    
                    if date_regex.match(posting_date) and date_regex.match(value_date):
                         current_txn = Transaction(
                            posting_date, 
                            value_date, 
                            description, 
                            ref_str, 
                            parse_amount(debit_str), 
                            parse_amount(credit_str), 
                            parse_amount(balance_str),
                            filename
                        )
            except Exception:
                pass
                
        elif current_txn:
            current_txn.description += " " + stripped_line

    if current_txn:
        transactions.append(current_txn)
        
    return transactions

# --- Streamlit UI ---

st.set_page_config(page_title="Bank Statement Merger", page_icon="🏦", layout="wide")

st.title("🏦 Bank Statement Merger Tool")
st.markdown("Upload multiple PDF statements to merge them into a single clean file.")

# Initialize session state for data persistence
if 'df' not in st.session_state:
    st.session_state.df = None

uploaded_files = st.file_uploader("Upload PDF Statements", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button(f"Process {len(uploaded_files)} Files"):
        all_transactions = []
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            file_bytes = uploaded_file.getvalue()
            txns = parse_pdf_from_bytes(file_bytes, uploaded_file.name)
            all_transactions.extend(txns)
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        unique_txns_map = {}
        for txn in all_transactions:
            key = txn.unique_key()
            if key not in unique_txns_map:
                unique_txns_map[key] = txn
        
        final_list = list(unique_txns_map.values())
        
        def parse_date_sort(t):
            try:
                return datetime.strptime(t.posting_date, "%d/%m/%Y")
            except:
                return datetime.min

        final_list.sort(key=parse_date_sort, reverse=True)
        
        data = [t.to_dict() for t in final_list]
        st.session_state.df = pd.DataFrame(data)
        st.success(f"Successfully processed! Found {len(final_list)} unique transactions.")

if st.session_state.df is not None:
    df = st.session_state.df

    st.divider()
    
    # Filtering Section
    st.subheader("🔍 Filter & Analysis")
    filter_text = st.text_input("Enter keywords to filter (e.g. thilini, tinylux, maypr)", placeholder="Enter words separated by commas...")
    
    display_df = df.copy()
    
    if filter_text:
        # Split by comma and clean up whitespace
        keywords = [k.strip() for k in filter_text.split(',') if k.strip()]
        if keywords:
            # Create a regex pattern: (word1|word2|word3)
            pattern = '|'.join([re.escape(k) for k in keywords])
            display_df = df[df['description'].str.contains(pattern, case=False, na=False)]
            st.info(f"Showing results containing: {', '.join(keywords)}")

    # Metrics for Displayed Data
    m_col1, m_col2, m_col3 = st.columns(3)
    if not display_df.empty:
        m_col1.metric("Record Count", len(display_df))
        m_col2.metric("Total Debit", f"{display_df['debit'].sum():,.2f}")
        m_col3.metric("Total Credit", f"{display_df['credit'].sum():,.2f}")
    else:
        st.warning("No records match the current filter.")

    # Display Table
    st.dataframe(display_df, use_container_width=True)
    
    # Download Section
    st.subheader("💾 Export Data")
    d_col1, d_col2 = st.columns(2)
    
    # Download JSON (Full or Filtered can be chosen, let's offer Filtered for JSON too if they want)
    json_data = display_df.to_dict(orient='records')
    json_str = json.dumps(json_data, indent=2)
    d_col1.download_button(
        label="Download Filtered JSON",
        data=json_str,
        file_name="filtered_statement.json",
        mime="application/json"
    )
    
    # Download CSV
    csv = display_df.to_csv(index=False).encode('utf-8')
    d_col2.download_button(
        label="Download Filtered CSV",
        data=csv,
        file_name="filtered_statement.csv",
        mime="text/csv"
    )

else:
    if not uploaded_files:
        st.info("Please upload one or more PDF files to begin.")
