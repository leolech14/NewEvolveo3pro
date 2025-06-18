"""ML-based FX rate prediction for international transactions."""

from __future__ import annotations

import joblib
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


class FXRatePredictor:
    """ML-based FX rate prediction for missing rates."""

    def __init__(self):
        self.model: Optional[GradientBoostingRegressor] = None
        self.scaler: Optional[StandardScaler] = None
        self.currency_averages: dict[str, float] = {}
        self.is_trained = False
        
        # Approximate historical ranges for validation
        self.currency_ranges = {
            'USD': (4.5, 6.5),  # USD/BRL typical range
            'EUR': (5.0, 7.0),  # EUR/BRL typical range
            'GBP': (6.0, 8.0),  # GBP/BRL typical range
        }

    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for FX rate prediction."""
        features = pd.DataFrame()
        
        # Amount-based features
        features['amount_brl'] = pd.to_numeric(data.get('amount_brl', 0), errors='coerce').fillna(0)
        features['amount_orig'] = pd.to_numeric(data.get('amount_orig', 0), errors='coerce').fillna(0)
        
        # Calculate implicit rate when both amounts are available
        features['implied_rate'] = np.where(
            (features['amount_orig'] > 0) & (features['amount_brl'] > 0),
            features['amount_brl'] / features['amount_orig'],
            0
        )
        
        # Currency encoding
        currencies = data.get('currency_orig', 'BRL').fillna('BRL')
        features['is_usd'] = (currencies == 'USD').astype(int)
        features['is_eur'] = (currencies == 'EUR').astype(int)
        features['is_gbp'] = (currencies == 'GBP').astype(int)
        
        # Date features (if available)
        if 'date' in data.columns:
            try:
                dates = pd.to_datetime(data['date'], errors='coerce')
                features['year'] = dates.dt.year.fillna(2024)
                features['month'] = dates.dt.month.fillna(1)
                features['day'] = dates.dt.day.fillna(1)
                features['quarter'] = dates.dt.quarter.fillna(1)
            except:
                # Fallback if date parsing fails
                features['year'] = 2024
                features['month'] = 10
                features['day'] = 15
                features['quarter'] = 4
        else:
            features['year'] = 2024
            features['month'] = 10
            features['day'] = 15
            features['quarter'] = 4
        
        # Amount magnitude features
        features['amount_brl_log'] = np.log1p(features['amount_brl'])
        features['amount_orig_log'] = np.log1p(features['amount_orig'])
        
        # Description-based features (simple)
        if 'description_text' in data.columns:
            descriptions = data['description_text'].fillna('')
            features['desc_length'] = descriptions.str.len()
            features['has_paypal'] = descriptions.str.contains('PAYPAL', case=False, na=False).astype(int)
            features['has_amazon'] = descriptions.str.contains('AMAZON', case=False, na=False).astype(int)
            features['has_online'] = descriptions.str.contains('ONLINE|INTERNET', case=False, na=False).astype(int)
        else:
            features['desc_length'] = 0
            features['has_paypal'] = 0
            features['has_amazon'] = 0
            features['has_online'] = 0
        
        return features

    def train(self, training_data: pd.DataFrame) -> dict:
        """Train the FX rate prediction model."""
        print("🔧 Training FX Rate Predictor...")
        
        # Filter for transactions with valid FX rates
        valid_fx = training_data[
            (pd.to_numeric(training_data.get('target_fx_rate', 0), errors='coerce') > 0) &
            (training_data.get('target_currency', '') != 'BRL') &
            (training_data.get('target_currency', '').notna())
        ].copy()
        
        if len(valid_fx) < 10:
            print("   ⚠️  Insufficient FX rate data for training")
            return {'error': 'Insufficient training data'}
        
        print(f"   • Training on {len(valid_fx)} FX transactions")
        
        # Prepare features and target
        X = self.prepare_features(valid_fx)
        y = pd.to_numeric(valid_fx['target_fx_rate'], errors='coerce')
        
        # Remove invalid targets
        valid_mask = (y > 0) & (y < 20)  # Reasonable FX rate range
        X = X[valid_mask]
        y = y[valid_mask]
        
        if len(X) < 5:
            print("   ⚠️  Insufficient valid FX rate data after filtering")
            return {'error': 'Insufficient valid data'}
        
        print(f"   • After filtering: {len(X)} valid transactions")
        print(f"   • FX rate range: {y.min():.3f} - {y.max():.3f}")
        
        # Calculate currency averages for fallback
        for currency in ['USD', 'EUR', 'GBP']:
            currency_mask = valid_fx['target_currency'] == currency
            if currency_mask.sum() > 0:
                avg_rate = y[currency_mask].mean()
                self.currency_averages[currency] = avg_rate
                print(f"   • Average {currency} rate: {avg_rate:.3f}")
        
        # Train-test split
        if len(X) > 10:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
        else:
            # Use all data for training if we have very few samples
            X_train, X_test, y_train, y_test = X, X, y, y
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        
        self.model.fit(X_train_scaled, y_train)
        self.is_trained = True
        
        # Evaluate
        train_pred = self.model.predict(X_train_scaled)
        test_pred = self.model.predict(X_test_scaled)
        
        train_mae = mean_absolute_error(y_train, train_pred)
        test_mae = mean_absolute_error(y_test, test_pred)
        train_r2 = r2_score(y_train, train_pred)
        test_r2 = r2_score(y_test, test_pred)
        
        print(f"   • Training MAE: {train_mae:.3f}, R²: {train_r2:.3f}")
        print(f"   • Test MAE: {test_mae:.3f}, R²: {test_r2:.3f}")
        
        return {
            'training_samples': len(X_train),
            'test_samples': len(X_test),
            'train_mae': train_mae,
            'test_mae': test_mae,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'currency_averages': self.currency_averages,
            'fx_range': (float(y.min()), float(y.max()))
        }

    def predict(self, data: pd.DataFrame) -> list[float]:
        """Predict FX rates for transactions."""
        if not self.is_trained:
            # Use fallback predictions based on currency averages
            return self._fallback_predict(data)
        
        # Prepare features
        X = self.prepare_features(data)
        X_scaled = self.scaler.transform(X)
        
        # Predict
        predictions = self.model.predict(X_scaled)
        
        # Post-process predictions with validation
        validated_predictions = []
        for i, pred in enumerate(predictions):
            currency = data.iloc[i].get('currency_orig', 'USD')
            validated_pred = self._validate_prediction(pred, currency)
            validated_predictions.append(validated_pred)
        
        return validated_predictions

    def _fallback_predict(self, data: pd.DataFrame) -> list[float]:
        """Fallback prediction using currency averages and heuristics."""
        predictions = []
        
        for _, row in data.iterrows():
            currency = row.get('currency_orig', 'USD')
            amount_brl = pd.to_numeric(row.get('amount_brl', 0), errors='coerce') or 0
            amount_orig = pd.to_numeric(row.get('amount_orig', 0), errors='coerce') or 0
            
            # Try to calculate from amounts first
            if amount_orig > 0 and amount_brl > 0:
                calculated_rate = amount_brl / amount_orig
                if self._is_reasonable_rate(calculated_rate, currency):
                    predictions.append(calculated_rate)
                    continue
            
            # Use currency averages
            if currency in self.currency_averages:
                predictions.append(self.currency_averages[currency])
            else:
                # Default rates
                default_rates = {'USD': 5.2, 'EUR': 5.8, 'GBP': 6.5}
                predictions.append(default_rates.get(currency, 5.2))
        
        return predictions

    def _validate_prediction(self, prediction: float, currency: str) -> float:
        """Validate and clamp prediction to reasonable range."""
        if currency in self.currency_ranges:
            min_rate, max_rate = self.currency_ranges[currency]
            return max(min_rate, min(max_rate, prediction))
        
        # General validation
        return max(1.0, min(20.0, prediction))

    def _is_reasonable_rate(self, rate: float, currency: str) -> bool:
        """Check if rate is within reasonable bounds."""
        if currency in self.currency_ranges:
            min_rate, max_rate = self.currency_ranges[currency]
            return min_rate <= rate <= max_rate
        
        return 1.0 <= rate <= 20.0

    def predict_single(self, amount_brl: float, amount_orig: float, currency: str, description: str = "") -> tuple[float, float]:
        """Predict FX rate for a single transaction with confidence."""
        # Create dataframe for single prediction
        data = pd.DataFrame([{
            'amount_brl': amount_brl,
            'amount_orig': amount_orig,
            'currency_orig': currency,
            'description_text': description
        }])
        
        predictions = self.predict(data)
        
        # Calculate confidence based on prediction method
        if amount_orig > 0 and amount_brl > 0:
            implied_rate = amount_brl / amount_orig
            if self._is_reasonable_rate(implied_rate, currency):
                return implied_rate, 0.95  # High confidence from calculation
        
        # ML or fallback prediction
        confidence = 0.7 if self.is_trained else 0.5
        return predictions[0], confidence

    def analyze_feature_importance(self) -> dict:
        """Analyze feature importance for FX rate prediction."""
        if not self.is_trained or self.model is None:
            return {'error': 'Model not trained'}
        
        # Mock feature names (should match prepare_features output)
        feature_names = [
            'amount_brl', 'amount_orig', 'implied_rate', 'is_usd', 'is_eur', 'is_gbp',
            'year', 'month', 'day', 'quarter', 'amount_brl_log', 'amount_orig_log',
            'desc_length', 'has_paypal', 'has_amazon', 'has_online'
        ]
        
        importances = self.model.feature_importances_
        feature_importance = list(zip(feature_names, importances))
        feature_importance.sort(key=lambda x: x[1], reverse=True)
        
        return {
            'feature_importance': feature_importance[:10],
            'total_features': len(feature_names)
        }

    def save_model(self, model_path: Path):
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'currency_averages': self.currency_averages,
            'currency_ranges': self.currency_ranges,
            'is_trained': self.is_trained
        }
        
        joblib.dump(model_data, model_path)
        print(f"   • FX model saved to {model_path}")

    def load_model(self, model_path: Path):
        """Load trained model from disk."""
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        model_data = joblib.load(model_path)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.currency_averages = model_data['currency_averages']
        self.currency_ranges = model_data.get('currency_ranges', self.currency_ranges)
        self.is_trained = model_data['is_trained']
        
        print(f"   • FX model loaded from {model_path}")
