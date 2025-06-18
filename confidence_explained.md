# 📊 Confidence Scores Explained

## What is Confidence?

**Confidence** is a percentage score (0-100%) that indicates how **reliable and accurate** an extraction result is likely to be.

Think of it as the system's "trust level" in its own results.

---

## 🎯 Confidence Ranges & Meaning

| **Confidence** | **Quality** | **Meaning** | **Action** |
|----------------|-------------|-------------|------------|
| **90-100%** | Excellent | Very reliable, high-quality extraction | ✅ Use as-is |
| **70-89%** | Good | Reliable with minor issues | ✅ Use with minimal review |
| **50-69%** | Fair | Acceptable but needs review | ⚠️ Review recommended |
| **30-49%** | Poor | Low quality, many issues | ⚠️ Manual verification needed |
| **0-29%** | Very Poor | Unreliable results | ❌ Consider re-processing |

---

## 🔍 How Confidence is Calculated

### Different Methods Use Different Factors:

### 1. **Cloud OCR Services** (Azure, AWS, Google)
```
Confidence = Average of:
- Character recognition certainty
- Layout detection accuracy  
- Field extraction confidence
- Text quality scores
```

**Example**: Azure gives each recognized word a confidence score, we average them.

### 2. **Table Detection** (Camelot)
```
Confidence = Based on:
- Table structure clarity
- Cell boundary detection
- Text alignment quality
- Number of tables found vs expected
```

**Example**: Clear table borders = higher confidence

### 3. **Pattern Matching** (Regex Fallback)
```
Confidence = Based on:
- Number of patterns matched
- Data completeness (dates, amounts, descriptions)
- Format consistency
- Field validation success
```

**Example**: Well-formatted transactions with all fields = higher confidence

### 4. **ML Models** (Category Classifier)
```
Confidence = Model's probability scores:
- How certain the model is about predictions
- Based on training data similarity
- Feature quality assessment
```

---

## 📈 Real Examples from Your System

### **Azure Document Intelligence: 95.2%**
```
✅ Very High Confidence
- OCR recognized text clearly
- Found structured data (tables/forms)
- Consistent formatting detected
- All key fields extracted successfully
→ Result: Highly reliable, use as-is
```

### **AWS Textract: 94.0%**
```
✅ Very High Confidence  
- Excellent text recognition
- Forms and tables detected well
- High character-level confidence
- Good layout understanding
→ Result: Highly reliable, minimal review needed
```

### **Camelot Tables: 84.3%**
```
✅ Good Confidence
- Tables detected successfully
- Clear cell boundaries
- Good text extraction
- Some minor formatting issues
→ Result: Reliable, quick review recommended
```

### **Fallback Regex: 30.0%**
```
⚠️ Poor Confidence
- Basic pattern matching only
- No layout understanding
- Missing some transaction details
- Backup method with limitations
→ Result: Works but needs verification
```

---

## 🎯 Why Confidence Matters

### 1. **Automatic Decision Making**
```python
if confidence > 90%:
    # Use results directly
elif confidence > 50%:
    # Use with human review
else:
    # Try different extraction method
```

### 2. **Fallback Triggering**
Your robust system uses confidence to decide when to fallback:
```
If primary_confidence < 10%:
    → Try secondary method
If secondary_confidence < 10%:
    → Try fallback method
```

### 3. **Quality Assurance**
- High confidence = Less manual review needed
- Low confidence = More quality control required

### 4. **Cost Optimization**
- High confidence local method = Skip expensive cloud processing
- Low confidence = May justify cloud processing cost

---

## 🧮 Confidence Calculation Examples

### **Example 1: Perfect OCR**
```
Document: Clear, high-quality scan
Characters recognized: 2,847 / 2,850 (99.9%)
Layout detected: Perfect tables
Fields extracted: All required fields found
→ Confidence: 96%
```

### **Example 2: Poor Quality Scan**
```
Document: Blurry, low-resolution
Characters recognized: 1,205 / 2,850 (42.3%)
Layout detected: Partial tables only
Fields extracted: Missing key data
→ Confidence: 23%
```

### **Example 3: Regex Pattern Matching**
```
Pattern matches: 58 transactions found
Complete data: 45 with all fields (77.6%)
Date format: 52 valid dates (89.7%)
Amount format: 55 valid amounts (94.8%)
→ Average confidence: 30% (conservative for pattern-based)
```

---

## 🚀 How Your System Uses Confidence

### **Intelligent Routing**
1. **Try Document AI** (if configured)
   - Expected: 90-98% confidence
2. **If fails or low confidence** → **Try Local Pipeline**
   - Expected: 70-85% confidence  
3. **If still low** → **Use Regex Fallback**
   - Expected: 20-40% confidence
4. **Always succeeds** with some level of extraction

### **Real-World Example**
```
Your Itaú Statement Processing:
1. Document AI: FAILED (billing issue)
2. Local Pipeline: 0% confidence (0 transactions)
3. Regex Fallback: 30% confidence (58 transactions)
→ Result: Success with known quality level
```

---

## 💡 Key Takeaways

1. **Confidence ≠ Accuracy**: A 30% confidence result might still be very useful
2. **Context Matters**: 30% from regex fallback is expected and acceptable
3. **Threshold Setting**: Your system uses 10% as fallback trigger (very conservative)
4. **Quality Indicator**: Helps you decide how much to trust/review results
5. **Process Improvement**: Low confidence indicates areas for system enhancement

**Bottom Line**: Confidence helps you understand **how much you can trust** the extraction results and **what level of review** they need.
