#!/bin/bash

# Function to start cron service
start_cron() {
    echo "Starting cron service..."
    
    # Load environment variables into crontab
    printenv | grep -v "no_proxy" | sed 's/^\(.*\)$/export \1/g' > /tmp/env.sh
    chmod +x /tmp/env.sh
    
    # Create the cron.log file and set permissions
    touch /var/log/cron.log
    chmod 0644 /var/log/cron.log
    
    # Load environment and install crontab
    cat /tmp/env.sh config/crontab | crontab -
    
    # Start cron in the background
    cron
    
    # Tail the log file in the foreground
    echo "Cron started, watching logs..."
    tail -f /var/log/cron.log
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