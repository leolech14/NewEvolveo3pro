#!/usr/bin/env python3
"""
Train Multi-Output Classifier (Category, Merchant, City)
=======================================================

Usage:
    python tools/train_multioutput_classifier.py \
        --goldens data/golden/golden_2024-10.csv data/golden/golden_2025-05.csv \
        --output src/ml/models/multioutput_classifier.joblib

- Trains a MultiOutputClassifier (RandomForest) to predict category, merchant, and city from transaction description.
- Uses TfidfVectorizer for text features.
- Prints accuracy and classification report for each field.
- Saves the trained model pipeline with joblib.
"""
import argparse
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib


def parse_args():
    parser = argparse.ArgumentParser(description="Train Multi-Output Classifier")
    parser.add_argument('--goldens', nargs='+', default=[
        'data/golden/golden_2024-10.csv',
        'data/golden/golden_2025-05.csv'], help='Paths to golden CSVs')
    parser.add_argument('--output', default='src/ml/models/multioutput_classifier.joblib', help='Output model path')
    return parser.parse_args()


def load_data(paths):
    dfs = [pd.read_csv(p, sep=None, engine='python') for p in paths]
    df = pd.concat(dfs, ignore_index=True)
    # Use desc_raw or description
    if 'desc_raw' in df.columns:
        X = df['desc_raw'].fillna("")
    elif 'description' in df.columns:
        X = df['description'].fillna("")
    else:
        raise ValueError("No description field found in golden CSVs.")
    y = df[['category', 'merchant_city', 'city']].fillna('UNKNOWN')
    # If merchant_city not present, fallback to merchant or blank
    if 'merchant_city' not in y.columns:
        y['merchant_city'] = df.get('merchant', pd.Series(['UNKNOWN']*len(df)))
    if 'city' not in y.columns:
        y['city'] = df.get('city', pd.Series(['UNKNOWN']*len(df)))
    return X, y


def main():
    args = parse_args()
    X, y = load_data(args.goldens)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y['category'])

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(max_features=1000)),
        ('clf', MultiOutputClassifier(RandomForestClassifier(n_estimators=200, random_state=42))),
    ])
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    y_pred_df = pd.DataFrame(y_pred, columns=y.columns)
    print("\nAccuracy and Classification Report by Field:")
    for col in y.columns:
        acc = accuracy_score(y_test[col], y_pred_df[col])
        print(f"\nField: {col}")
        print(f"  Accuracy: {acc:.2%}")
        print(classification_report(y_test[col], y_pred_df[col]))
    # Save model
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, args.output)
    print(f"\nModel saved to {args.output}")

if __name__ == "__main__":
    main() 