#!/usr/bin/env python3
"""
Interactive Extraction Dashboard
===============================

Usage:
    python tools/generate_dashboard.py [--port 8051]

- Loads error analysis and enrichment results from 10outputs/.
- Visualizes per-field accuracy, error types, and enrichment improvements interactively.
- Runs a Plotly Dash web app locally.
"""
import os
import argparse
import pandas as pd
import plotly.express as px
import dash
from dash import dcc, html, Input, Output
from pathlib import Path

# Helper to load all error reports and enrichment results
def load_reports(base_dir="10outputs"):
    records = []
    for extractor in os.listdir(base_dir):
        csv_dir = Path(base_dir) / extractor / "csv"
        if not csv_dir.exists():
            continue
        for file in csv_dir.glob("*_error_report.csv"):
            pdf = file.stem.replace("_error_report", "")
            df = pd.read_csv(file)
            df['extractor'] = extractor
            df['pdf'] = pdf
            records.append(df)
        for file in csv_dir.glob("*_enriched.csv"):
            pdf = file.stem.replace("_enriched", "")
            df = pd.read_csv(file, sep=';')
            df['extractor'] = extractor
            df['pdf'] = pdf
            df['is_enriched'] = True
            records.append(df)
    if records:
        return pd.concat(records, ignore_index=True)
    return pd.DataFrame()

def main():
    parser = argparse.ArgumentParser(description="Interactive Extraction Dashboard")
    parser.add_argument('--port', type=int, default=8050, help='Port to run the dashboard on (default: 8050)')
    args = parser.parse_args()
    port = args.port
    df = load_reports()
    if df.empty:
        print("No reports found in 10outputs/. Run the pipeline first.")
        return
    app = dash.Dash(__name__)
    extractors = df['extractor'].unique()
    pdfs = df['pdf'].unique()
    fields = [c for c in df.columns if c not in ['extractor', 'pdf', 'is_enriched']]
    app.layout = html.Div([
        html.H1("Extraction & Enrichment Dashboard"),
        html.Label("Extractor:"),
        dcc.Dropdown(
            id='extractor-dropdown',
            options=[{'label': e, 'value': e} for e in extractors],
            value=extractors[0],
        ),
        html.Label("PDF:"),
        dcc.Dropdown(
            id='pdf-dropdown',
            options=[{'label': p, 'value': p} for p in pdfs],
            value=pdfs[0],
        ),
        html.Label("Field:"),
        dcc.Dropdown(
            id='field-dropdown',
            options=[{'label': f, 'value': f} for f in fields],
            value=fields[0],
        ),
        dcc.Graph(id='accuracy-graph'),
        dcc.Graph(id='enrichment-graph'),
    ])

    @app.callback(
        Output('accuracy-graph', 'figure'),
        [Input('extractor-dropdown', 'value'),
         Input('pdf-dropdown', 'value'),
         Input('field-dropdown', 'value')]
    )
    def update_accuracy_graph(extractor, pdf, field):
        dff = df[(df['extractor'] == extractor) & (df['pdf'] == pdf)]
        if 'accuracy' in dff.columns:
            fig = px.bar(dff, x='field', y='accuracy', color='field', title=f'Field Accuracy for {extractor} - {pdf}')
        else:
            fig = px.histogram(dff, x=field, title=f'Distribution of {field} for {extractor} - {pdf}')
        return fig

    @app.callback(
        Output('enrichment-graph', 'figure'),
        [Input('extractor-dropdown', 'value'),
         Input('pdf-dropdown', 'value'),
         Input('field-dropdown', 'value')]
    )
    def update_enrichment_graph(extractor, pdf, field):
        dff = df[(df['extractor'] == extractor) & (df['pdf'] == pdf)]
        if 'is_enriched' in dff.columns:
            fig = px.histogram(dff, x=field, color='is_enriched', barmode='group',
                               title=f'Enrichment Comparison for {field} ({extractor} - {pdf})')
        else:
            fig = px.histogram(dff, x=field, title=f'Distribution of {field} for {extractor} - {pdf}')
        return fig

    print(f"\nDashboard running at http://127.0.0.1:{port}/ (Ctrl+C to stop)")
    app.run_server(debug=True, port=port)

if __name__ == "__main__":
    main() 