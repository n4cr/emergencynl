from typing import List, Optional, Dict
from datetime import datetime, timedelta
from instructor import OpenAISchema
from pydantic import Field
import instructor
from openai import OpenAI
import sqlite3
import json
import os
from collections import defaultdict

# Initialize instructor-wrapped client
client = instructor.patch(OpenAI())

def get_db_connection():
    db_path = os.path.join('data', 'p2000.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

class IncidentCluster(OpenAISchema):
    """A cluster of related incidents"""
    cluster_type: str = Field(..., description="Type of incidents in this cluster (e.g., 'Traffic Accidents', 'Medical Emergencies')")
    incident_count: int = Field(..., description="Number of incidents in this cluster")
    peak_hours: List[int] = Field(..., description="Hours with highest incident frequency")
    regions: List[str] = Field(..., description="Affected regions")
    severity_assessment: str = Field(..., description="High/Medium/Low based on incident types and frequency")
    key_patterns: List[str] = Field(..., description="Key patterns or commonalities in these incidents")

class IncidentHighlight(OpenAISchema):
    """A significant highlight from the incidents"""
    title: str = Field(..., description="Brief title of the highlight")
    description: str = Field(..., description="Detailed description of why this is significant")
    severity: str = Field(..., description="High/Medium/Low severity assessment")
    affected_areas: List[str] = Field(..., description="Areas/regions affected by this highlight")

class IncidentTrend(OpenAISchema):
    """Identified trend in the incidents"""
    trend_name: str = Field(..., description="Name of the identified trend")
    description: str = Field(..., description="Description of the trend and its implications")
    supporting_evidence: List[str] = Field(..., description="List of evidence supporting this trend")

class DailyIncidentAnalysis(OpenAISchema):
    """Complete analysis of incidents for a day"""
    date: datetime = Field(..., description="Date of the analysis")
    total_incidents: int = Field(..., description="Total number of incidents analyzed")
    key_highlights: List[IncidentHighlight] = Field(..., description="Key highlights from the day's incidents")
    identified_trends: List[IncidentTrend] = Field(..., description="Trends identified from the incidents")
    summary: str = Field(..., description="Overall summary of the day's incidents")
    recommendations: List[str] = Field(..., description="Recommendations based on the analysis")

def get_incident_clusters(conn: sqlite3.Connection, start_date: datetime, end_date: datetime) -> Dict:
    """Get incident clusters and statistics using SQL aggregation."""
    
    # Get service type clusters with counts and sample incidents
    service_clusters = conn.execute("""
        WITH RankedIncidents AS (
            SELECT 
                *,
                ROW_NUMBER() OVER (PARTITION BY service_type ORDER BY timestamp) as rn
            FROM incidents
            WHERE timestamp >= ? AND timestamp < ?
        )
        SELECT 
            service_type,
            COUNT(*) as incident_count,
            GROUP_CONCAT(DISTINCT region) as regions,
            json_group_array(
                json_object(
                    'timestamp', timestamp,
                    'service_type', service_type,
                    'region', region,
                    'message', message,
                    'details', details
                )
            ) as sample_incidents
        FROM (
            SELECT * FROM RankedIncidents WHERE rn <= 5
        )
        GROUP BY service_type
    """, (start_date, end_date)).fetchall()
    
    # Get hourly distribution
    hourly_stats = conn.execute("""
        SELECT 
            service_type,
            strftime('%H', timestamp) as hour,
            COUNT(*) as count
        FROM incidents
        WHERE timestamp >= ? AND timestamp < ?
        GROUP BY service_type, hour
        ORDER BY service_type, count DESC
    """, (start_date, end_date)).fetchall()
    
    # Get regional distribution
    regional_stats = conn.execute("""
        SELECT 
            service_type,
            region,
            COUNT(*) as count
        FROM incidents
        WHERE timestamp >= ? AND timestamp < ?
        GROUP BY service_type, region
        ORDER BY service_type, count DESC
    """, (start_date, end_date)).fetchall()
    
    # Process hourly stats into peak hours
    peak_hours = defaultdict(list)
    for stat in hourly_stats:
        if len(peak_hours[stat['service_type']]) < 3:  # Keep top 3 hours
            peak_hours[stat['service_type']].append(int(stat['hour']))
    
    # Process results into clusters
    clusters = []
    for cluster in service_clusters:
        sample_incidents = json.loads(cluster['sample_incidents'])
        regions = [r.strip() for r in cluster['regions'].split(',')]
        
        # Create cluster prompt
        incidents_text = "\n".join([
            f"Incident {i+1}:\n" + "\n".join(f"{k}: {v}" for k, v in incident.items())
            for i, incident in enumerate(sample_incidents)
        ])
        
        prompt = f"""Analyze this cluster of {cluster['incident_count']} {cluster['service_type']} incidents:

Sample incidents:
{incidents_text}

Additional information:
- Peak hours: {peak_hours[cluster['service_type']]}
- Regions involved: {regions}
- Total incidents in cluster: {cluster['incident_count']}

Identify patterns and assess severity."""

        # Get cluster analysis
        cluster_analysis = client.chat.completions.create(
            model="gpt-4-1106-preview",
            response_model=IncidentCluster,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        clusters.append(cluster_analysis)
    
    return clusters

def analyze_daily_incidents(incidents: List[dict], date: datetime) -> DailyIncidentAnalysis:
    """
    Analyze incidents for a day using database-level aggregation
    
    Args:
        incidents: List of incident dictionaries (used only for total count)
        date: Date of the incidents
    
    Returns:
        DailyIncidentAnalysis object containing structured analysis
    """
    start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    
    with get_db_connection() as conn:
        # Get overall statistics
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_incidents,
                COUNT(DISTINCT region) as unique_regions,
                COUNT(DISTINCT service_type) as unique_services
            FROM incidents
            WHERE timestamp >= ? AND timestamp < ?
        """, (start_date, end_date)).fetchone()
        
        # Get clusters using database aggregation
        clusters = get_incident_clusters(conn, start_date, end_date)
        
        # Prepare final analysis prompt with cluster insights
        clusters_text = "\n".join([
            f"Cluster: {c.cluster_type}\n"
            f"Count: {c.incident_count}\n"
            f"Severity: {c.severity_assessment}\n"
            f"Patterns: {', '.join(c.key_patterns)}\n"
            f"Regions: {', '.join(c.regions)}\n"
            for c in clusters
        ])
        
        prompt = f"""Analyze these incident clusters from {date.strftime('%Y-%m-%d')}:

Clusters:
{clusters_text}

Statistics:
- Total incidents: {stats['total_incidents']}
- Unique regions: {stats['unique_regions']}
- Service types: {stats['unique_services']}

Provide a comprehensive analysis including key highlights, trends, and recommendations."""

        # Get final analysis
        analysis = client.chat.completions.create(
            model="gpt-4-1106-preview",
            response_model=DailyIncidentAnalysis,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        return analysis

def init_analysis_tables():
    """Initialize the database tables for incident analysis"""
    with get_db_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS incident_analysis (
            date TEXT PRIMARY KEY,
            total_incidents INTEGER,
            summary TEXT,
            recommendations TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS incident_highlights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            title TEXT,
            description TEXT,
            severity TEXT,
            affected_areas TEXT,
            FOREIGN KEY (date) REFERENCES incident_analysis(date)
        )
        """)
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS incident_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            trend_name TEXT,
            description TEXT,
            supporting_evidence TEXT,
            FOREIGN KEY (date) REFERENCES incident_analysis(date)
        )
        """)
        conn.commit()

# Initialize tables
init_analysis_tables()

def store_analysis(analysis: DailyIncidentAnalysis):
    """Store the incident analysis in the database"""
    date_str = analysis.date.strftime('%Y-%m-%d')
    
    with get_db_connection() as conn:
        # Store main analysis
        conn.execute("""
        INSERT OR REPLACE INTO incident_analysis 
        (date, total_incidents, summary, recommendations)
        VALUES (?, ?, ?, ?)
        """, (
            date_str,
            analysis.total_incidents,
            analysis.summary,
            json.dumps(analysis.recommendations)
        ))
        
        # Clear existing highlights and trends for this date
        conn.execute("DELETE FROM incident_highlights WHERE date = ?", (date_str,))
        conn.execute("DELETE FROM incident_trends WHERE date = ?", (date_str,))
        
        # Store highlights
        for highlight in analysis.key_highlights:
            conn.execute("""
            INSERT INTO incident_highlights 
            (date, title, description, severity, affected_areas)
            VALUES (?, ?, ?, ?, ?)
            """, (
                date_str,
                highlight.title,
                highlight.description,
                highlight.severity,
                json.dumps(highlight.affected_areas)
            ))
        
        # Store trends
        for trend in analysis.identified_trends:
            conn.execute("""
            INSERT INTO incident_trends
            (date, trend_name, description, supporting_evidence)
            VALUES (?, ?, ?, ?)
            """, (
                date_str,
                trend.trend_name,
                trend.description,
                json.dumps(trend.supporting_evidence)
            ))
        
        conn.commit()

def get_stored_analysis(date: datetime) -> Optional[dict]:
    """Retrieve stored analysis for a given date"""
    date_str = date.strftime('%Y-%m-%d')
    
    with get_db_connection() as conn:
        # Get main analysis
        analysis = conn.execute(
            "SELECT * FROM incident_analysis WHERE date = ?",
            (date_str,)
        ).fetchone()
        
        if not analysis:
            return None
        
        # Get highlights
        highlights = conn.execute(
            "SELECT * FROM incident_highlights WHERE date = ?",
            (date_str,)
        ).fetchall()
        
        # Get trends
        trends = conn.execute(
            "SELECT * FROM incident_trends WHERE date = ?",
            (date_str,)
        ).fetchall()
        
        return {
            "date": date_str,
            "total_incidents": analysis['total_incidents'],
            "summary": analysis['summary'],
            "recommendations": json.loads(analysis['recommendations']),
            "highlights": [
                {
                    "title": h['title'],
                    "description": h['description'],
                    "severity": h['severity'],
                    "affected_areas": json.loads(h['affected_areas'])
                }
                for h in highlights
            ],
            "trends": [
                {
                    "name": t['trend_name'],
                    "description": t['description'],
                    "evidence": json.loads(t['supporting_evidence'])
                }
                for t in trends
            ]
        }

def get_incident_insights(incidents: List[dict], date: Optional[datetime] = None) -> dict:
    """
    Get insights and analysis for a list of incidents
    
    Args:
        incidents: List of incident dictionaries
        date: Optional date for the analysis, defaults to current date
    
    Returns:
        Dictionary containing structured analysis and insights
    """
    if date is None:
        date = datetime.now()
    
    # Check if analysis exists for this date
    stored_analysis = get_stored_analysis(date)
    if stored_analysis:
        return stored_analysis
        
    # If no stored analysis, generate new one
    analysis = analyze_daily_incidents(incidents, date)
    
    # Store the analysis
    store_analysis(analysis)
    
    return {
        "date": analysis.date.strftime("%Y-%m-%d"),
        "total_incidents": analysis.total_incidents,
        "highlights": [
            {
                "title": h.title,
                "description": h.description,
                "severity": h.severity,
                "affected_areas": h.affected_areas
            }
            for h in analysis.key_highlights
        ],
        "trends": [
            {
                "name": t.trend_name,
                "description": t.description,
                "evidence": t.supporting_evidence
            }
            for t in analysis.identified_trends
        ],
        "summary": analysis.summary,
        "recommendations": analysis.recommendations
    }
