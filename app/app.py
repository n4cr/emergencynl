from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import sqlite3
from typing import Dict, List, Optional
import os
from .ai import get_incident_insights

# Create the Flask app first
app = Flask(__name__)

def get_db_connection():
    # Get database path from environment variable, fallback to data directory
    db_path = os.getenv('DB_PATH', os.path.join('data', 'p2000.db'))
    app.logger.info(f"Connecting to database at: {db_path}")
    
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Initialize the database tables if they don't exist
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                service_type TEXT NOT NULL,
                region TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,
                raw_timestamp TEXT NOT NULL,
                UNIQUE(timestamp, service_type, region, message)
            )
        """)
    
    return conn

# Initialize the app
with app.app_context():
    # Ensure database and tables exist
    with get_db_connection() as conn:
        pass  # The connection function now handles table creation

def get_available_regions() -> List[str]:
    """Get list of all available regions from the database."""
    with get_db_connection() as conn:
        regions = conn.execute(
            "SELECT DISTINCT region FROM incidents ORDER BY region"
        ).fetchall()
        return [row['region'] for row in regions]

def get_data_for_date(date: datetime, region: Optional[str] = None) -> Dict:
    """Get P2000 data for a specific date and optional region."""
    start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = (start_date + timedelta(days=1))
    
    with get_db_connection() as conn:
        # Get all incidents for the day to pass to analysis
        incidents_query = f"""
            SELECT * FROM incidents 
            WHERE timestamp >= ? AND timestamp < ?
            {' AND region = ?' if region else ''}
            ORDER BY timestamp
        """
        incidents_params = [start_date, end_date]
        if region:
            incidents_params.append(region)
            
        incidents = [dict(row) for row in conn.execute(incidents_query, incidents_params).fetchall()]
        
        # Get AI analysis for the day
        analysis = get_incident_insights(incidents, start_date)
        
        # Build base query parts
        base_conditions = "timestamp >= ? AND timestamp < ?"
        base_params = [start_date, end_date]
        
        # Add region filter if specified
        if region:
            base_conditions += " AND region = ?"
            base_params.append(region)
        
        # Get total incidents
        total = conn.execute(
            f"SELECT COUNT(*) as count FROM incidents WHERE {base_conditions}",
            base_params
        ).fetchone()['count']
        
        # Get service type counts and trends
        def get_service_count_and_trend(service_type: str) -> Dict:
            current = conn.execute(
                f"SELECT COUNT(*) as count FROM incidents WHERE service_type = ? AND {base_conditions}",
                [service_type] + base_params
            ).fetchone()['count']
            
            previous_start = start_date - timedelta(days=7)
            previous_params = [service_type, previous_start, start_date]
            if region:
                previous_params.append(region)
            
            previous = conn.execute(
                f"SELECT COUNT(*) as count FROM incidents WHERE service_type = ? AND timestamp >= ? AND timestamp < ? {' AND region = ?' if region else ''}",
                previous_params
            ).fetchone()['count']
            
            previous_daily_avg = previous / 7 if previous > 0 else 1
            trend_pct = ((current - previous_daily_avg) / previous_daily_avg * 100) if previous_daily_avg > 0 else 0
            
            trend = f"+{trend_pct:.0f}%" if trend_pct > 0 else f"{trend_pct:.0f}%" if trend_pct < 0 else "Stable"
            
            return {
                "count": current,
                "trend": trend
            }
        
        # Get timeline data
        timeline = {
            'Ambulance': {},
            'Politie': {},
            'Brandweer': {}
        }
        for hour in range(24):
            hour_start = start_date + timedelta(hours=hour)
            hour_end = hour_start + timedelta(hours=1)
            hour_key = f"{hour:02d}:00"
            
            for service_type in ['Ambulance', 'Politie', 'Brandweer']:
                hour_params = [service_type, hour_start, hour_end]
                if region:
                    hour_params.append(region)
                
                count = conn.execute(
                    f"SELECT COUNT(*) as count FROM incidents WHERE service_type = ? AND timestamp >= ? AND timestamp < ? {' AND region = ?' if region else ''}",
                    hour_params
                ).fetchone()['count']
                timeline[service_type][hour_key] = count
        
        # Get category breakdown
        category_query = f"""
            SELECT service_type, COUNT(*) as count 
            FROM incidents 
            WHERE {base_conditions}
            GROUP BY service_type
        """
        categories = conn.execute(category_query, base_params).fetchall()
        category_breakdown = {row['service_type']: row['count'] for row in categories}
        
        # Get hotspots (regions with most incidents)
        hotspot_query = f"""
            SELECT region, COUNT(*) as incidents
            FROM incidents
            WHERE {base_conditions}
            GROUP BY region
            ORDER BY incidents DESC
            LIMIT 5
        """
        hotspots = conn.execute(hotspot_query, base_params).fetchall()
        
        # Get 7-day trend data
        trend_data = []
        for i in range(7, -1, -1):
            day_start = start_date - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            day_params = [day_start, day_end]
            if region:
                day_params.append(region)
            
            day_count = conn.execute(
                f"SELECT COUNT(*) as count FROM incidents WHERE timestamp >= ? AND timestamp < ? {' AND region = ?' if region else ''}",
                day_params
            ).fetchone()['count']
            
            trend_data.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'count': day_count
            })
        
        return {
            "total_incidents": total,
            "ambulance": get_service_count_and_trend("Ambulance"),
            "police": get_service_count_and_trend("Politie"),
            "fire": get_service_count_and_trend("Brandweer"),
            "timeline": timeline,
            "category_breakdown": category_breakdown,
            "hotspots": [
                {"location": row['region'], "incidents": row['incidents']}
                for row in hotspots
            ],
            "trend_data": trend_data,
            "analysis": analysis
        }

@app.route('/')
def index():
    try:
        # Get query parameters with defaults
        date_str = request.args.get('date', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
        region = request.args.get('region', None)
        
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            selected_date = datetime.now() - timedelta(days=1)
        
        data = get_data_for_date(selected_date, region)
        regions = get_available_regions()
        
        return render_template('index.html', 
                             data=data, 
                             date=selected_date.strftime('%B %d, %Y'),
                             regions=regions,
                             selected_region=region,
                             selected_date=selected_date.strftime('%Y-%m-%d'))
    except sqlite3.OperationalError as e:
        app.logger.error(f"Database error: {str(e)}")
        return render_template('error.html', 
                             message="Database error. Please ensure the scraper has run at least once."), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return render_template('error.html', 
                             message="An unexpected error occurred."), 500

@app.route('/api/data')
def get_data():
    date_str = request.args.get('date', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))
    region = request.args.get('region', None)
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        selected_date = datetime.now() - timedelta(days=1)
    
    return jsonify(get_data_for_date(selected_date, region))

@app.route('/health/')
def health():
    """Health check endpoint for monitoring."""
    try:
        # Test database connection
        with get_db_connection() as conn:
            conn.execute('SELECT 1').fetchone()
        return jsonify({'status': 'healthy'}), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True) 