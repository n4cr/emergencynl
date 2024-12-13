#!/bin/bash

# Function to start cron service
start_cron() {
    echo "Starting cron service..."
    
    # Load environment variables into crontab
    printenv | grep -v "no_proxy" | sed 's/^\(.*\)$/export \1/g' > /tmp/env.sh
    chmod +x /tmp/env.sh
    
    # Load environment and install crontab
    cat /tmp/env.sh config/crontab | crontab -
    
    # Start cron in foreground with output to stdout
    echo "Starting cron in foreground..."
    exec cron -f -L 15
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