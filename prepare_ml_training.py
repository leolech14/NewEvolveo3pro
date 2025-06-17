#!/usr/bin/env python3
"""Prepare ML training data from both 2024-10 and 2025-05 golden datasets."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.ml.training_data_prep import TrainingDataPreparator


def main():
    """Prepare comprehensive ML training data from both golden datasets."""
    print("🚀 Preparing ML Training Data from Golden Datasets")
    
    preparator = TrainingDataPreparator()
    
    # Both golden datasets
    golden_files = [
        Path("data/golden/golden_2024-10.csv"),  # 43 transactions
        Path("data/golden/golden_2025-05.csv"),  # 212 transactions
    ]
    
    # Check files exist
    for file_path in golden_files:
        if not file_path.exists():
            print(f"❌ Golden file not found: {file_path}")
            return
        print(f"✅ Found golden file: {file_path}")
    
    print(f"\n📊 Analyzing Data Quality...")
    analysis = preparator.analyze_golden_data_quality(golden_files)
    
    print(f"📈 Total Transactions: {analysis['total_transactions']}")
    print(f"   • 2024-10: 43 transactions")
    print(f"   • 2025-05: 212 transactions") 
    print(f"   • Combined: {analysis['total_transactions']} transactions")
    
    print(f"\n🔍 Field Completeness:")
    for field, completeness in analysis['field_completeness'].items():
        percentage = completeness * 100
        status = "✅" if percentage > 80 else "⚠️" if percentage > 50 else "❌"
        print(f"   {status} {field}: {percentage:.1f}%")
    
    print(f"\n📊 Category Distribution:")
    for category, count in analysis['category_distribution'].items():
        if category:  # Skip empty categories
            print(f"   • {category}: {count} transactions")
    
    print(f"\n💱 Currency Distribution:")
    for currency, count in analysis['currency_distribution'].items():
        if currency:  # Skip empty currencies
            print(f"   • {currency}: {count} transactions")
    
    # Load all transactions and create features
    print(f"\n🔧 Creating ML Training Features...")
    all_transactions = []
    
    for file_path in golden_files:
        transactions = preparator.load_golden_transactions(file_path)
        print(f"   • Loaded {len(transactions)} from {file_path.name}")
        all_transactions.extend(transactions)
    
    # Create feature vectors
    features = preparator.create_training_features(all_transactions)
    print(f"   • Created {len(features)} feature vectors")
    
    # Export training data
    output_path = Path("data/ml_training_data.csv")
    preparator.export_training_data(features, output_path)
    
    print(f"\n🎯 ML Training Data Preparation Complete!")
    print(f"   • Total dataset: {len(all_transactions)} transactions")
    print(f"   • Feature vectors: {len(features)}")
    print(f"   • Training file: {output_path}")
    
    # Show sample features for verification
    if features:
        print(f"\n📋 Sample Feature Vector:")
        sample = features[0]
        for key, value in list(sample.items())[:10]:  # Show first 10 features
            print(f"   • {key}: {value}")
        print(f"   • ... and {len(sample) - 10} more features")
    
    # Training recommendations
    print(f"\n💡 ML Training Recommendations:")
    print(f"   • Use stratified split to maintain category distribution")
    print(f"   • Consider class imbalance for rare categories")
    print(f"   • Text features (description) ideal for NLP models")
    print(f"   • Amount patterns good for amount-based predictions")
    print(f"   • With {len(all_transactions)} samples, suitable for ML training")


if __name__ == "__main__":
    main()
