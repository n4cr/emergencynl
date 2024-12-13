from typing import List, Optional
from datetime import datetime
from instructor import OpenAISchema
from pydantic import Field
import instructor
from openai import OpenAI
import sqlite3
import json
import os

# Initialize instructor-wrapped client
client = instructor.patch(OpenAI())

def get_db_connection():
    db_path = os.path.join('data', 'p2000.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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

def analyze_daily_incidents(incidents: List[dict], date: datetime) -> DailyIncidentAnalysis:
    """
    Analyze a list of incidents for a given day and provide structured insights
    
    Args:
        incidents: List of incident dictionaries containing details
        date: Date of the incidents
    
    Returns:
        DailyIncidentAnalysis object containing structured analysis
    """
    # Prepare the prompt with incident information
    incidents_text = "\n".join([
        f"Incident {i+1}:\n" + "\n".join(f"{k}: {v}" for k, v in incident.items())
        for i, incident in enumerate(incidents)
    ])
    
    prompt = f"""Analyze the following incidents from {date.strftime('%Y-%m-%d')}:

{incidents_text}

Provide a comprehensive analysis including key highlights, trends, and recommendations."""

    # Use instructor to get structured analysis
    analysis = client.chat.completions.create(
        model="gpt-4-1106-preview",
        response_model=DailyIncidentAnalysis,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    return analysis

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
