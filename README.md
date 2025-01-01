# Dutch Emergency Services

A real-time P2000 emergency services monitoring dashboard for the Netherlands. This application scrapes P2000 emergency messages and presents them in an interactive dashboard.

## Features

- Real-time monitoring of P2000 emergency messages
- Interactive dashboard with incident statistics
- Regional filtering capabilities
- Historical data analysis
- Automatic data collection every minute
- Docker containerized for easy deployment

## Architecture

The application consists of two main components:

1. **Web Application (Flask)**
   - Serves the dashboard interface
   - Provides data visualization
   - Handles API requests for incident data

2. **Scraper Service**
   - Runs on a configurable schedule (default: every minute)
   - Collects P2000 messages
   - Stores data in SQLite database
   - Configurable through crontab

## Prerequisites

- Docker
- Docker Compose

## Setup & Installation

1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd emergencynl
   ```

2. Create a data directory for the SQLite database:
   ```bash
   mkdir data
   ```

3. Build and start the containers:
   ```bash
   docker-compose up --build
   ```

The application will be available at `http://localhost:5001`

## Configuration

### Scraper Schedule

The scraper schedule can be modified by editing the `crontab` file. The default configuration runs every minute and collects data from the last 30 minutes:

```bash
# Run scraper every minute
* * * * * cd /app && /usr/local/bin/python -m app.scraper --minutes 30 >> /var/log/cron.log 2>&1
```

Common cron patterns:
- `* * * * *` - every minute
- `*/5 * * * *` - every 5 minutes
- `0 * * * *` - every hour
- `0 0 * * *` - every day at midnight

### Docker Configuration

The application uses two Docker containers:

1. **Web Container** (`Dockerfile`)
   - Runs the Flask application
   - Exposes port 5001
   - Mounts the data directory

2. **Scraper Container** (`Dockerfile.scraper`)
   - Runs the data collection service
   - Shares the data directory with the web container
   - Configurable through mounted crontab file

## Directory Structure

```
emergencynl/
├── app/
│   ├── app.py          # Flask application
│   ├── scraper.py      # P2000 data scraper
│   └── templates/      # HTML templates
├── data/               # SQLite database directory
├── Dockerfile          # Web application container
├── Dockerfile.scraper  # Scraper container
├── docker-compose.yml  # Container orchestration
├── crontab            # Scraper schedule configuration
└── requirements.txt    # Python dependencies
```

## Monitoring & Maintenance

### Viewing Logs

```bash
# View web application logs
docker-compose logs web

# View scraper logs
docker-compose logs scraper

# Follow logs in real-time
docker-compose logs -f
```

### Container Management

```bash
# Start containers
docker-compose up -d

# Stop containers
docker-compose down

# Rebuild and start containers
docker-compose up --build

# View container status
docker-compose ps
```

### Database

The SQLite database is stored in the `data` directory and is shared between containers. Make sure to back up this directory if you need to preserve the data.
