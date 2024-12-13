#!/bin/bash

# Function to start cron service
start_cron() {
    echo "Starting cron service..."
    
    # Load environment variables into crontab
    env | grep -v "no_proxy" > /tmp/env.txt
    cat /tmp/env.txt config/crontab | crontab -
    rm /tmp/env.txt
    
    # Start cron and redirect its output to stdout
    cron -f 2>&1
}

# Function to start web service
start_web() {
    echo "Starting web service..."
    exec gunicorn -b 0.0.0.0:8000 --config gunicorn.conf.py wsgi:app
}

# Check the command argument
case "$1" in
    "cron")
        start_cron
        ;;
    "web" | "")
        start_web
        ;;
    *)
        echo "Unknown command: $1"
        echo "Usage: $0 {web|cron}"
        exit 1
        ;;
esac 