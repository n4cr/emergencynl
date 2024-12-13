import click
from datetime import datetime, timedelta
import sqlite3
from typing import Dict, List
import os
from .ai import get_incident_insights
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

def get_db_connection():
    # Get database path from environment variable, fallback to data directory
    db_path = os.getenv('DB_PATH', os.path.join('data', 'p2000.db'))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_incidents_for_date(date: datetime) -> List[Dict]:
    """Get all incidents for a specific date."""
    start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    
    with get_db_connection() as conn:
        incidents = conn.execute("""
            SELECT * FROM incidents 
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp
        """, (start_date, end_date)).fetchall()
        
        return [dict(incident) for incident in incidents]

@click.group()
def cli():
    """Command line interface for Emergency NL analysis."""
    pass

@cli.command()
@click.option('--date', '-d', default=None, 
              help='Date to analyze in YYYY-MM-DD format. Defaults to yesterday.')
@click.option('--force', '-f', is_flag=True, 
              help='Force re-analysis even if already exists.')
def analyze(date: str, force: bool):
    """Run AI analysis for incidents on a specific date."""
    try:
        if date:
            analysis_date = datetime.strptime(date, '%Y-%m-%d')
        else:
            analysis_date = datetime.now() - timedelta(days=1)
            
        with console.status(f"[bold blue]Analyzing incidents for {analysis_date.strftime('%Y-%m-%d')}..."):
            # Get incidents
            incidents = get_incidents_for_date(analysis_date)
            if not incidents:
                console.print(f"[yellow]No incidents found for {analysis_date.strftime('%Y-%m-%d')}[/yellow]")
                return
                
            # Run analysis
            analysis = get_incident_insights(incidents, analysis_date)
            
            # Display results
            console.print(f"\n[bold green]Analysis for {analysis['date']}[/bold green]\n")
            
            # Summary
            console.print("[bold]Summary[/bold]")
            console.print(analysis['summary'])
            console.print()
            
            # Highlights
            highlight_table = Table(title="Key Highlights", box=box.ROUNDED)
            highlight_table.add_column("Title", style="cyan")
            highlight_table.add_column("Severity", style="bold")
            highlight_table.add_column("Description")
            highlight_table.add_column("Areas", style="italic")
            
            for highlight in analysis['highlights']:
                severity_style = {
                    'High': 'red',
                    'Medium': 'yellow',
                    'Low': 'green'
                }.get(highlight['severity'], 'white')
                
                highlight_table.add_row(
                    highlight['title'],
                    f"[{severity_style}]{highlight['severity']}[/{severity_style}]",
                    highlight['description'],
                    ", ".join(highlight['affected_areas'])
                )
            console.print(highlight_table)
            console.print()
            
            # Trends
            console.print("[bold]Identified Trends[/bold]")
            for trend in analysis['trends']:
                console.print(f"[cyan]{trend['name']}[/cyan]")
                console.print(trend['description'])
                console.print("\nSupporting Evidence:")
                for evidence in trend['evidence']:
                    console.print(f"• {evidence}")
                console.print()
            
            # Recommendations
            console.print("[bold]Recommendations[/bold]")
            for i, rec in enumerate(analysis['recommendations'], 1):
                console.print(f"{i}. {rec}")
            
    except ValueError as e:
        console.print(f"[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

def main():
    """Entry point for direct Python execution."""
    cli()

if __name__ == '__main__':
    main() 