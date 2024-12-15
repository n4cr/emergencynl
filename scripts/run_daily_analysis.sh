#!/bin/bash

# Get yesterday's date in YYYY-MM-DD format
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)

# Run the analysis command
python -m app.cli analyze -f --date $YESTERDAY 