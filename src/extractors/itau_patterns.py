#!/usr/bin/env python3
"""
Road-tested regex patterns and utilities for Itaú Personnalité statements.
Based on production field manual.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ItauTransaction:
    """Structured Itaú transaction with bounding box."""
    date: str
    merchant: str
    amount_brl: float
    category: str = ""
    city: str = ""
    amount_original: Optional[float] = None
    currency_original: str = ""
    fx_rate: Optional[float] = None
    card_last4: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1)


class ItauPatterns:
    """Road-tested patterns for Itaú statement parsing."""
    
    # Proven regex patterns from field manual
    RE_DOM = re.compile(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d.,]+)$')
    RE_CAT = re.compile(r'^([A-ZÇÉÂÕ ]+)\.\s+([A-ZÂÁÉÍÓÚÊÔÛ .-]+)$')
    RE_CARD = re.compile(r'LEONARDO B LECH \(final (\d{4})\)')
    RE_FX = re.compile(r'Dólar de Conversão R\$\s*([\d.,]+)')
    
    # International patterns
    RE_INTL_LINE1 = re.compile(r'^(\d{2}/\d{2})\s+(.+?)\s+([\d.,]+)$')  # date merchant usd
    RE_INTL_LINE2 = re.compile(r'^([A-ZÂÁÉÍÓÚÊÔÛ .-]+)\s+([\d.,]+)\s+([A-Z]{3})\s+([\d.,]+)$')  # city orig_amount currency brl_amount
    
    @staticmethod
    def parse_amount(amount_str: str) -> Optional[float]:
        """Parse Brazilian currency amount."""
        try:
            # Remove thousands separators (.) and replace decimal comma with dot
            cleaned = amount_str.replace('.', '').replace(',', '.')
            return float(cleaned)
        except (ValueError, AttributeError):
            return None
    
    @staticmethod
    def normalize_date(date_str: str) -> str:
        """Normalize DD/MM to YYYY-MM-DD."""
        try:
            current_year = datetime.now().year
            day, month = date_str.split('/')
            return f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"
        except (ValueError, AttributeError):
            return date_str
    
    @staticmethod
    def group_by_y(words: List[Dict], tolerance: float = 3.0) -> List[List[Dict]]:
        """Group words by Y coordinate (for line detection)."""
        if not words:
            return []
        
        # Sort by Y coordinate (top to bottom)
        sorted_words = sorted(words, key=lambda w: w.get('top', w.get('y0', 0)))
        
        rows = []
        current_row = [sorted_words[0]]
        current_y = sorted_words[0].get('top', sorted_words[0].get('y0', 0))
        
        for word in sorted_words[1:]:
            word_y = word.get('top', word.get('y0', 0))
            
            if abs(word_y - current_y) <= tolerance:
                current_row.append(word)
            else:
                # Sort current row by X coordinate (left to right)
                current_row.sort(key=lambda w: w.get('x0', w.get('left', 0)))
                rows.append(current_row)
                current_row = [word]
                current_y = word_y
        
        # Add final row
        if current_row:
            current_row.sort(key=lambda w: w.get('x0', w.get('left', 0)))
            rows.append(current_row)
        
        return rows
    
    @staticmethod
    def words_to_text(words: List[Dict]) -> str:
        """Convert word list to text string."""
        return ' '.join(w.get('text', '') for w in words if w.get('text', '').strip())
    
    @staticmethod
    def calculate_bbox(words: List[Dict]) -> Tuple[float, float, float, float]:
        """Calculate bounding box for a group of words."""
        if not words:
            return (0, 0, 0, 0)
        
        x0s = [w.get('x0', w.get('left', 0)) for w in words]
        y0s = [w.get('top', w.get('y0', 0)) for w in words]
        x1s = [w.get('x1', w.get('right', 0)) for w in words]
        y1s = [w.get('bottom', w.get('y1', 0)) for w in words]
        
        return (min(x0s), min(y0s), max(x1s), max(y1s))
    
    @classmethod
    def parse_domestic_transaction(cls, line1_words: List[Dict], line2_words: List[Dict], 
                                 card_last4: str = "") -> Optional[ItauTransaction]:
        """Parse domestic 2-line transaction."""
        line1_text = cls.words_to_text(line1_words)
        line2_text = cls.words_to_text(line2_words)
        
        # Parse line 1: date merchant amount
        match1 = cls.RE_DOM.match(line1_text)
        if not match1:
            return None
        
        date_str, merchant, amount_str = match1.groups()
        
        # Parse line 2: category city
        match2 = cls.RE_CAT.match(line2_text)
        if not match2:
            return None
        
        category, city = match2.groups()
        
        # Parse amount
        amount = cls.parse_amount(amount_str)
        if amount is None:
            return None
        
        # Calculate combined bounding box
        all_words = line1_words + line2_words
        bbox = cls.calculate_bbox(all_words)
        
        return ItauTransaction(
            date=cls.normalize_date(date_str),
            merchant=merchant.strip(),
            amount_brl=amount,
            category=category.strip(),
            city=city.strip(),
            card_last4=card_last4,
            bbox=bbox
        )
    
    @classmethod
    def parse_international_transaction(cls, line1_words: List[Dict], line2_words: List[Dict], 
                                      line3_words: List[Dict], card_last4: str = "") -> Optional[ItauTransaction]:
        """Parse international 3-line transaction."""
        line1_text = cls.words_to_text(line1_words)
        line2_text = cls.words_to_text(line2_words)
        line3_text = cls.words_to_text(line3_words)
        
        # Parse line 1: date merchant usd
        match1 = cls.RE_INTL_LINE1.match(line1_text)
        if not match1:
            return None
        
        date_str, merchant, usd_str = match1.groups()
        
        # Parse line 2: city orig_amount currency brl_amount
        match2 = cls.RE_INTL_LINE2.match(line2_text)
        if not match2:
            return None
        
        city, orig_amount_str, currency, brl_amount_str = match2.groups()
        
        # Parse line 3: FX rate
        fx_match = cls.RE_FX.search(line3_text)
        fx_rate = cls.parse_amount(fx_match.group(1)) if fx_match else None
        
        # Parse amounts
        amount_brl = cls.parse_amount(brl_amount_str)
        amount_original = cls.parse_amount(orig_amount_str)
        
        if amount_brl is None:
            return None
        
        # Calculate combined bounding box
        all_words = line1_words + line2_words + line3_words
        bbox = cls.calculate_bbox(all_words)
        
        return ItauTransaction(
            date=cls.normalize_date(date_str),
            merchant=merchant.strip(),
            amount_brl=amount_brl,
            category="INTERNACIONAL",
            city=city.strip(),
            amount_original=amount_original,
            currency_original=currency,
            fx_rate=fx_rate,
            card_last4=card_last4,
            bbox=bbox
        )
    
    @classmethod
    def extract_card_last4(cls, text: str) -> str:
        """Extract card last 4 digits."""
        match = cls.RE_CARD.search(text)
        return match.group(1) if match else ""
    
    @classmethod
    def is_transaction_line(cls, text: str) -> bool:
        """Check if line looks like a transaction."""
        # Must start with date pattern
        return bool(re.match(r'^\d{2}/\d{2}\s+', text))
    
    @classmethod
    def is_category_line(cls, text: str) -> bool:
        """Check if line looks like a category/city line."""
        return bool(cls.RE_CAT.match(text))
