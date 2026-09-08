"""Stage 5: Clean and normalize extracted text (strip headers/footers, normalize whitespace, fix OCR artifacts)."""
import re
import unicodedata

# Common ligatures and replacements
LIGATURE_MAP = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "—": "-",
    "–": "-",
}

# Regex patterns for headers, footers, and page numbers
PAGE_NUMBER_PATTERNS = [
    r'(?i)^\s*page\s+\d+\s*(?:of\s*\d+)?\s*$',
    r'^\s*[-—–]\s*\d+\s*[-—–]\s*$',
    r'^\s*\[\s*\d+\s*\]\s*$',
    r'^\s*\d+\s*/\s*\d+\s*$',
]

# Boilerplate patterns to strip
BOILERPLATE_PATTERNS = [
    r'(?i)^\s*confidential\s*(?:and\s*proprietary)?\s*$',
    r'(?i)^\s*all rights reserved\.?\s*$',
]


# Plain-English: Normalizes special characters and symbols.
# 1. Unpacks typographic ligatures where joined letters became a single character (e.g. 'ﬁ' -> 'fi', 'ﬂ' -> 'fl').
# 2. Converts fancy curly "smart quotes" and em/en dashes into standard keyboard quotes (" and ') and hyphens (-).
# 3. Applies Unicode NFKC normalization so accented letters and symbols have consistent internal representations.
def normalize_unicode(text: str) -> str:
    """Normalize unicode characters and replace common ligatures and stylized quotes."""
    for char, replacement in LIGATURE_MAP.items():
        text = text.replace(char, replacement)
    return unicodedata.normalize("NFKC", text)


# Plain-English: Cleans up optical scanning glitches and visual noise produced by OCR.
# 1. Deletes unreadable replacement characters ('\ufffd' or the '' symbol) from failed scans.
# 2. Replaces excessively long runs of delimiter lines (e.g. "========" or "--------") with a clean "---".
# 3. Drops isolated lines containing only stray punctuation noise (e.g. speckles like ". ," or ";") with no letters or numbers.
def fix_ocr_artifacts(text: str) -> str:
    """Correct common OCR scanning noise and artifacts."""
    # Replace unicode replacement character
    text = text.replace("\ufffd", "")
    # Remove excessive repeated delimiter lines e.g. "------" or "======="
    text = re.sub(r'[-_=~]{4,}', '---', text)
    # Remove isolated non-alphanumeric noise on its own line
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        # Skip lines that are just random punctuation noise e.g. ". , ; ."
        if trimmed and len(trimmed) <= 3 and not re.search(r'[A-Za-z0-9]', trimmed):
            continue
        lines.append(line)
    return "\n".join(lines)


# Plain-English: Detects and strips recurring non-content header and footer lines.
# 1. Strips standalone page numbers in various formats (e.g. "Page 1 of 5", "- 2 -", "[ 3 ]", "4 / 10").
# 2. Strips repetitive boilerplate phrases like "CONFIDENTIAL", "Confidential and Proprietary", and "All rights reserved".
def strip_headers_footers(text: str) -> str:
    """Filter out repeating header/footer artifacts such as page numbers."""
    cleaned_lines = []
    for line in text.splitlines():
        line_clean = line.strip()
        
        # Check against page numbers
        is_page_num = any(re.match(p, line_clean) for p in PAGE_NUMBER_PATTERNS)
        if is_page_num:
            continue
            
        # Check against common boilerplate headers
        is_boilerplate = any(re.match(p, line_clean) for p in BOILERPLATE_PATTERNS)
        if is_boilerplate:
            continue

        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


# Plain-English: Cleans up spacing, tabs, and line breaks across the whole document.
# 1. Standardizes Windows (\r\n) and legacy Mac (\r) line returns into Unix newlines (\n).
# 2. Converts tabs and irregular Unicode spacing (like non-breaking spaces '\u00A0') into standard ASCII spaces.
# 3. Collapses multiple consecutive spaces into a single space and trims whitespace from line edges.
# 4. Reduces 3 or more blank lines down to 2, keeping clean paragraph spacing without giant empty gaps.
def normalize_whitespace(text: str) -> str:
    """Collapse tabs and irregular spaces, trimming line ends, and limiting consecutive newlines."""
    # Replace carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace non-breaking spaces and tabs with standard space
    text = re.sub(r'[\t\u00A0\u1680\u2000-\u200a\u202f\u205f\u3000]', ' ', text)
    # Collapse multiple horizontal spaces to single space
    text = re.sub(r'[ ]{2,}', ' ', text)
    # Trim lines
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    # Collapse 3 or more newlines down to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Plain-English: The master cleaning pipeline that orchestrates all 4 cleaning stages in order:
# 1. Normalizes Unicode characters, ligatures, and quotes.
# 2. Fixes OCR scanning glitches and speckle noise.
# 3. Removes page numbers and boilerplate headers/footers.
# 4. Standardizes spacing and paragraph line breaks.
def clean_extracted_text(raw_text: str) -> str:
    """Run full cleaning pipeline on raw extracted text."""
    if not raw_text:
        return ""
    text = normalize_unicode(raw_text)
    text = fix_ocr_artifacts(text)
    text = strip_headers_footers(text)
    text = normalize_whitespace(text)
    return text
