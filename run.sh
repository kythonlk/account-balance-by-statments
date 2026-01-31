#!/bin/bash

# Ensure pip is installed
if ! command -v pip &> /dev/null; then
    echo "pip could not be found, please install it."
    exit 1
fi

echo "Installing dependencies..."
pip install streamlit pandas -q

echo "Starting App..."
echo "Your browser should open automatically. If not, click the link below."
streamlit run app.py
