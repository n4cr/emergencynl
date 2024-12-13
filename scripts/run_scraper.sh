#!/bin/bash

# Debug: Print current directory and PYTHONPATH
pwd
cd /app
echo "PYTHONPATH: $PYTHONPATH"

# Add the project root directory to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/app"

# Debug: Print updated PYTHONPATH
echo "Updated PYTHONPATH: $PYTHONPATH"

# Set default values if environment variables are not set
SCRAPER_INTERVAL=${SCRAPER_INTERVAL:-30}
SCRAPER_DELAY=${SCRAPER_DELAY:-1.0}

echo "Running scraper with interval: ${SCRAPER_INTERVAL} minutes, delay: ${SCRAPER_DELAY} seconds"

# Run the scraper with explicit arguments
/usr/local/bin/python -m app.scraper --minutes "${SCRAPER_INTERVAL}" --delay "${SCRAPER_DELAY}"