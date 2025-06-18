"""NLP-based merchant city extraction from transaction descriptions."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
from pathlib import Path


class MerchantCityExtractor:
    """NLP-based merchant and city extraction."""

    def __init__(self):
        self.brazilian_cities = set()
        self.common_merchants = set()
        self.trained_patterns = []
        self.is_trained = False
        
        # Common Brazilian city patterns
        self.city_patterns = [
            r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s+(?:SP|RJ|MG|RS|PR|SC|BA|PE|CE|GO|AM|PA|MT|MS|ES|PB|RN|AL|SE|AC|RO|RR|AP|TO|DF)\b',
            r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\s+BR\b',
            r'\b([A-Z][A-Z\s]+)\s+BR\b',
            r'\b(SAO PAULO|RIO DE JANEIRO|BELO HORIZONTE|SALVADOR|BRASILIA|FORTALEZA|MANAUS|CURITIBA|RECIFE|PORTO ALEGRE)\b',
            r'\s+([A-Z]{2,}(?:\s+[A-Z]{2,})*)\s*$',  # City at end
        ]
        
        # Merchant patterns
        self.merchant_patterns = [
            r'^([A-Z][A-Za-z\s&\.]+?)(?:\s+\d|\s+[A-Z]{2,}\s|$)',  # Merchant before numbers/city
            r'^([A-Z][A-Za-z\s&\.]{3,20})',  # First capitalized words
        ]
        
        # Online indicators
        self.online_indicators = {
            'PAYPAL', 'AMAZON', 'NETFLIX', 'SPOTIFY', 'UBER', 'IFOOD', 'INTERNET', 'ONLINE', 'WEB'
        }

    def train(self, training_data: pd.DataFrame) -> dict:
        """Train the extractor using golden data."""
        print("🔧 Training Merchant City Extractor...")
        
        # Extract patterns from training data
        cities_found = set()
        merchants_found = set()
        
        for _, row in training_data.iterrows():
            description = row.get('description_text', '')
            target_city = row.get('target_merchant_city', '')
            
            if target_city and target_city.strip():
                cities_found.add(target_city.strip().upper())
                
                # Learn patterns from this example
                city_position = description.upper().find(target_city.upper())
                if city_position > 0:
                    # Extract potential merchant before city
                    potential_merchant = description[:city_position].strip()
                    if len(potential_merchant) > 3:
                        merchants_found.add(potential_merchant.upper())
        
        self.brazilian_cities = cities_found
        self.common_merchants = merchants_found
        self.is_trained = True
        
        print(f"   • Learned {len(cities_found)} cities")
        print(f"   • Learned {len(merchants_found)} merchant patterns")
        print(f"   • Top cities: {list(sorted(cities_found))[:10]}")
        
        return {
            'cities_learned': len(cities_found),
            'merchants_learned': len(merchants_found),
            'sample_cities': list(sorted(cities_found))[:10],
            'sample_merchants': list(sorted(merchants_found))[:5]
        }

    def extract_city(self, description: str) -> Optional[str]:
        """Extract city from transaction description."""
        if not description:
            return None
        
        description = description.strip()
        
        # Check for online transactions first
        desc_upper = description.upper()
        if any(indicator in desc_upper for indicator in self.online_indicators):
            return "ONLINE"
        
        # Try learned cities first
        if self.is_trained:
            for city in self.brazilian_cities:
                if city in desc_upper:
                    return city
        
        # Try regex patterns
        for pattern in self.city_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                city = match.group(1).strip().upper()
                # Filter out obvious non-cities
                if len(city) > 2 and not city.isdigit():
                    # Additional validation
                    if not any(word in city for word in ['CARTAO', 'FINAL', 'CARD']):
                        return city
        
        return None

    def extract_merchant(self, description: str) -> Optional[str]:
        """Extract merchant from transaction description."""
        if not description:
            return None
        
        description = description.strip()
        desc_upper = description.upper()
        
        # Check for known merchants
        if self.is_trained:
            for merchant in self.common_merchants:
                if merchant in desc_upper:
                    return merchant
        
        # Try regex patterns
        for pattern in self.merchant_patterns:
            match = re.search(pattern, description)
            if match:
                merchant = match.group(1).strip()
                # Clean up merchant name
                merchant = re.sub(r'\s+', ' ', merchant)
                if len(merchant) > 3:
                    return merchant.title()
        
        return None

    def extract_merchant_and_city(self, description: str) -> tuple[Optional[str], Optional[str]]:
        """Extract both merchant and city from description."""
        city = self.extract_city(description)
        merchant = self.extract_merchant(description)
        
        # If we found a city, try to extract merchant from the part before city
        if city and city != "ONLINE":
            city_pos = description.upper().find(city.upper())
            if city_pos > 0:
                merchant_part = description[:city_pos].strip()
                if len(merchant_part) > 3:
                    merchant = merchant_part.title()
        
        return merchant, city

    def analyze_patterns(self, descriptions: list[str]) -> dict:
        """Analyze patterns in descriptions for improvement."""
        results = {
            'total_descriptions': len(descriptions),
            'cities_extracted': 0,
            'merchants_extracted': 0,
            'online_transactions': 0,
            'empty_descriptions': 0,
            'sample_extractions': []
        }
        
        for desc in descriptions[:100]:  # Sample first 100
            if not desc or not desc.strip():
                results['empty_descriptions'] += 1
                continue
            
            merchant, city = self.extract_merchant_and_city(desc)
            
            if city:
                results['cities_extracted'] += 1
                if city == "ONLINE":
                    results['online_transactions'] += 1
            
            if merchant:
                results['merchants_extracted'] += 1
            
            if len(results['sample_extractions']) < 10:
                results['sample_extractions'].append({
                    'description': desc,
                    'merchant': merchant,
                    'city': city
                })
        
        results['city_extraction_rate'] = results['cities_extracted'] / len(descriptions) if descriptions else 0
        results['merchant_extraction_rate'] = results['merchants_extracted'] / len(descriptions) if descriptions else 0
        
        return results

    def enhance_description(self, description: str) -> dict:
        """Enhance a description with extracted merchant and city info."""
        merchant, city = self.extract_merchant_and_city(description)
        
        return {
            'original_description': description,
            'extracted_merchant': merchant,
            'extracted_city': city,
            'is_online': city == "ONLINE" if city else False,
            'enhanced_description': f"{merchant} - {city}" if merchant and city else description
        }

    def save_patterns(self, patterns_path: Path):
        """Save learned patterns to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained patterns")
        
        patterns_data = {
            'brazilian_cities': list(self.brazilian_cities),
            'common_merchants': list(self.common_merchants),
            'is_trained': self.is_trained
        }
        
        import json
        with open(patterns_path, 'w', encoding='utf-8') as f:
            json.dump(patterns_data, f, ensure_ascii=False, indent=2)
        
        print(f"   • Patterns saved to {patterns_path}")

    def load_patterns(self, patterns_path: Path):
        """Load patterns from disk."""
        if not patterns_path.exists():
            raise FileNotFoundError(f"Patterns file not found: {patterns_path}")
        
        import json
        with open(patterns_path, 'r', encoding='utf-8') as f:
            patterns_data = json.load(f)
        
        self.brazilian_cities = set(patterns_data['brazilian_cities'])
        self.common_merchants = set(patterns_data['common_merchants'])
        self.is_trained = patterns_data['is_trained']
        
        print(f"   • Patterns loaded from {patterns_path}")
        print(f"   • Cities: {len(self.brazilian_cities)}, Merchants: {len(self.common_merchants)}")
