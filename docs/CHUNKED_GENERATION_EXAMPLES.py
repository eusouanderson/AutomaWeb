"""
Example: Using the Chunked Test Generation Architecture

This example demonstrates how to use the refactored architecture
to generate Robot Framework tests from DOM while managing token limits.
"""

import asyncio
import json
from pathlib import Path

from app.core.config import settings
from app.domain.dom.models import DOMSectionType
from app.domain.dom.preprocessor import DOMPreprocessor
from app.domain.dom.segmenter import DOMSegmenter
from app.infrastructure.llm_chunking.chunker import AdaptiveChunker, ChunkingStrategy


# ============================================================================
# EXAMPLE 1: Basic Preprocessing
# ============================================================================

def example_1_preprocessing():
    """Reduce token usage by preprocessing DOM."""
    print("\n=== EXAMPLE 1: DOM Preprocessing ===\n")
    
    # Simulate raw page structure from scanner
    raw_page_structure = {
        "url": "https://example.com",
        "dom_tree": {
            "tag": "html",
            "attributes": {
                "lang": "en",
                "style": "font-family: Arial; color: #000; margin: 0; padding: 0;",
                "class": "navbar navbar-light navbar-expand-lg m-0 p-0 d-flex justify-content-between",
                "id": "root",
            },
            "children": [
                {
                    "tag": "header",
                    "attributes": {
                        "id": "main-header",
                        "class": "header sticky-top bg-primary",
                        "role": "banner",
                    },
                    "text": "Welcome to Example",
                    "children": [
                        {
                            "tag": "button",
                            "attributes": {
                                "id": "menu-toggle",
                                "type": "button",
                                "class": "btn btn-primary",
                                "onclick": "toggleMenu()",
                                "aria-label": "Toggle navigation menu",
                            },
                            "text": "Menu",
                        }
                    ],
                },
                {
                    "tag": "main",
                    "attributes": {
                        "id": "main-content",
                        "role": "main",
                    },
                    "children": [
                        {
                            "tag": "form",
                            "attributes": {
                                "id": "login-form",
                                "method": "post",
                                "class": "form",
                            },
                            "children": [
                                {
                                    "tag": "input",
                                    "attributes": {
                                        "type": "email",
                                        "name": "email",
                                        "id": "email-input",
                                        "placeholder": "Enter your email",
                                        "required": "true",
                                    },
                                },
                                {
                                    "tag": "input",
                                    "attributes": {
                                        "type": "password",
                                        "name": "password",
                                        "id": "password-input",
                                        "placeholder": "Enter password",
                                        "required": "true",
                                    },
                                },
                            ],
                        }
                    ],
                },
            ],
        },
    }
    
    # Create preprocessor
    preprocessor = DOMPreprocessor(max_text_per_element=200)
    
    # Show sizes before/after
    original_json = json.dumps(raw_page_structure)
    print(f"Original size: {len(original_json):,} bytes")
    
    # Preprocess
    preprocessed = preprocessor.preprocess_page_structure(raw_page_structure)
    
    preprocessed_json = json.dumps(preprocessed)
    print(f"Preprocessed size: {len(preprocessed_json):,} bytes")
    print(f"Reduction: {(1 - len(preprocessed_json)/len(original_json)) * 100:.1f}%\n")
    
    # Show example of cleaned attributes
    print("Example: Original button attributes:")
    print(json.dumps(raw_page_structure["dom_tree"]["children"][0]["children"][0]["attributes"], indent=2))
    
    print("\nExample: Preprocessed button attributes:")
    preprocessed_header = preprocessed["dom_tree"]["children"][0]
    print(json.dumps(preprocessed_header["children"][0], indent=2))


# ============================================================================
# EXAMPLE 2: DOM Segmentation
# ============================================================================

def example_2_segmentation():
    """Identify logical page sections for independent processing."""
    print("\n=== EXAMPLE 2: DOM Segmentation ===\n")
    
    # Simulate preprocessed page structure
    page_structure = {
        "url": "https://example.com",
        "dom_tree": {
            "tag": "html",
            "children": [
                {
                    "tag": "header",
                    "id": "main-header",
                    "text": "Site Header",
                    "children": [
                        {"tag": "button", "text": "Menu", "id": "menu-btn"},
                        {"tag": "img", "id": "logo"},
                    ],
                },
                {
                    "tag": "nav",
                    "id": "main-nav",
                    "children": [
                        {"tag": "a", "href": "/", "text": "Home"},
                        {"tag": "a", "href": "/about", "text": "About"},
                        {"tag": "a", "href": "/contact", "text": "Contact"},
                    ],
                },
                {
                    "tag": "main",
                    "id": "content",
                    "children": [
                        {
                            "tag": "form",
                            "id": "contact-form",
                            "children": [
                                {"tag": "input", "type": "text", "name": "name", "placeholder": "Your name"},
                                {"tag": "input", "type": "email", "name": "email", "placeholder": "Your email"},
                                {"tag": "button", "type": "submit", "text": "Send"},
                            ],
                        }
                    ],
                },
                {
                    "tag": "footer",
                    "id": "main-footer",
                    "text": "© 2024 Example Inc.",
                },
            ],
        },
    }
    
    # Create segmenter
    segmenter = DOMSegmenter()
    
    # Segment page
    result = segmenter.segment_page(page_structure)
    
    print(f"Found {len(result.sections)} sections:\n")
    for i, section in enumerate(result.sections, 1):
        print(f"{i}. {section.section_type.value.upper()}: {section.name}")
        print(f"   Elements: {len(section.elements)}")
        print(f"   Size: ~{section.estimate_char_size():,} chars\n")


# ============================================================================
# EXAMPLE 3: DOM Chunking for Token Limits
# ============================================================================

def example_3_chunking():
    """Split sections into token-safe chunks."""
    print("\n=== EXAMPLE 3: DOM Chunking ===\n")
    
    # Simulate segmented sections
    from app.domain.dom.models import DOMSection, ProcessedElement
    
    # Create a form section with multiple elements
    form_elements = [
        ProcessedElement(tag="input", type="text", name="username", placeholder="Username"),
        ProcessedElement(tag="input", type="password", name="password", placeholder="Password"),
        ProcessedElement(tag="input", type="checkbox", name="remember", xpath="//*[@id='remember']"),
        ProcessedElement(tag="button", text="Login", type="submit"),
        ProcessedElement(tag="a", href="/forgot-password", text="Forgot password?"),
    ]
    
    form_section = DOMSection(
        section_type=DOMSectionType.FORMS,
        name="Login Form",
        elements=form_elements,
    )
    
    # Create chunker with specific token budget
    strategy = ChunkingStrategy(
        target_chunk_chars=2000,
        reserve_chars=500,
        max_chunk_count=5,
    )
    
    chunker = AdaptiveChunker(
        total_token_budget=30000,  # Budget for all chunks
        strategy=strategy,
    )
    
    # Chunk the section
    chunks = chunker.chunk_section(form_section)
    
    print(f"Section: {form_section.name}")
    print(f"Total size: {form_section.estimate_char_size():,} chars")
    print(f"Created {len(chunks)} chunk(s):\n")
    
    for i, chunk in enumerate(chunks, 1):
        tokens = chunker.estimate_tokens(chunk.char_size)
        print(f"Chunk {i}:")
        print(f"  ID: {chunk.chunk_id}")
        print(f"  Size: {chunk.char_size:,} chars (~{tokens} tokens)")
        print(f"  Elements: {len(chunk.elements)}")
        print(f"  Priority: {chunk.priority}\n")


# ============================================================================
# EXAMPLE 4: Chunk-based LLM Processing Prompt
# ============================================================================

def example_4_chunk_prompt():
    """Show how chunks are sent to LLM."""
    print("\n=== EXAMPLE 4: Chunk-based LLM Processing ===\n")
    
    from app.domain.dom.models import DOMChunk, DOMSectionType, ProcessedElement
    
    # Create a sample chunk
    chunk = DOMChunk(
        chunk_id="forms_0",
        section_type=DOMSectionType.FORMS,
        section_name="Login Form",
        elements=[
            ProcessedElement(
                tag="input",
                type="email",
                name="email",
                placeholder="Enter email",
                xpath="//input[@name='email']",
            ),
            ProcessedElement(
                tag="input",
                type="password",
                name="password",
                placeholder="Enter password",
                xpath="//input[@name='password']",
            ),
            ProcessedElement(
                tag="button",
                text="Login",
                type="submit",
                xpath="//button[@type='submit']",
            ),
        ],
        char_size=450,
        priority=10,
    )
    
    # Show the JSON that gets sent to LLM
    print("CHUNK DATA SENT TO LLM:")
    print("=" * 60)
    chunk_json = json.dumps(chunk.to_dict(), indent=2)
    print(chunk_json)
    
    print("\n" + "=" * 60)
    print("\nEXAMPLE PROMPT STRUCTURE:")
    print("=" * 60)
    
    prompt = f"""Generate Robot Framework tests for the forms section

Section name: {chunk.section_name}
Number of elements: {len(chunk.elements)}

User request: Generate test cases for user login functionality

Focus on:
- Login form validation
- Email field interaction
- Password field interaction
- Submit button functionality
- Error handling for invalid credentials
"""
    
    print(prompt)


# ============================================================================
# EXAMPLE 5: Test Aggregation
# ============================================================================

def example_5_aggregation():
    """Show how tests from multiple chunks are merged."""
    print("\n=== EXAMPLE 5: Test Aggregation ===\n")
    
    # Simulate generated tests from different sections
    header_test = """*** Test Cases ***
Test Header - Logo Click
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Load State    networkidle
    Click    id=logo
    URL Should Be    https://example.com/
    Close Browser
"""
    
    forms_test = """*** Test Cases ***
Test Forms - Login Submit
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Load State    networkidle
    Fill Text    id=email-input    user@example.com
    Fill Text    id=password-input    password123
    Click    id=login-btn
    URL Should Be    https://example.com/dashboard
    Close Browser
"""
    
    nav_test = """*** Test Cases ***
Test Navigation - About Link
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Load State    networkidle
    Click    //a[text()='About']
    URL Should Be    https://example.com/about
    Close Browser
"""
    
    print("TESTS FROM DIFFERENT SECTIONS:")
    print("=" * 60)
    print("\n1. HEADER SECTION:")
    print(header_test)
    
    print("\n2. FORMS SECTION:")
    print(forms_test)
    
    print("\n3. NAVIGATION SECTION:")
    print(nav_test)
    
    print("\n" + "=" * 60)
    print("\nAFTER AGGREGATION AND DEDUPLICATION:")
    print("=" * 60)
    
    merged = """*** Settings ***
Library    Browser
Suite Teardown    Close Browser

*** Test Cases ***
Test Header - Logo Click
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Load State    networkidle
    Click    id=logo
    URL Should Be    https://example.com/
    Close Browser

Test Forms - Login Submit
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Load State    networkidle
    Fill Text    id=email-input    user@example.com
    Fill Text    id=password-input    password123
    Click    id=login-btn
    URL Should Be    https://example.com/dashboard
    Close Browser

Test Navigation - About Link
    New Browser    chromium
    New Context
    New Page    https://example.com
    Wait For Load State    networkidle
    Click    //a[text()='About']
    URL Should Be    https://example.com/about
    Close Browser
"""
    
    print(merged)


# ============================================================================
# EXAMPLE 6: Full Pipeline
# ============================================================================

async def example_6_full_pipeline():
    """Complete example of the chunked generation pipeline."""
    print("\n=== EXAMPLE 6: Full Pipeline ===\n")
    
    from app.infrastructure.llm_chunking.orchestrator import ChunkedTestGenerationOrchestrator
    from app.models.test_request import TestRequest
    
    print("Pipeline steps:")
    print("1. ✓ Preprocess DOM (remove noise)")
    print("2. ✓ Segment into sections (header, nav, main, forms, etc.)")
    print("3. ✓ Chunk sections (respect token limits)")
    print("4. ✓ Process chunks through LLM (parallel)")
    print("5. ✓ Merge results (deduplicate, aggregate)")
    print("6. ✓ Return final Robot Framework test suite")
    
    print("\nBenefits:")
    print("• Reduced token usage (chunking large DOMs)")
    print("• Better organization (section-based)")
    print("• Parallel processing (faster generation)")
    print("• Better test quality (focused chunks)")
    print("• Graceful degradation (partial failures handled)")
    print("• Caching (avoid reprocessing)")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run all examples."""
    print("╔" + "=" * 58 + "╗")
    print("║" + " CHUNKED TEST GENERATION ARCHITECTURE - EXAMPLES ".center(58) + "║")
    print("╚" + "=" * 58 + "╝")
    
    example_1_preprocessing()
    example_2_segmentation()
    example_3_chunking()
    example_4_chunk_prompt()
    example_5_aggregation()
    asyncio.run(example_6_full_pipeline())
    
    print("\n" + "=" * 60)
    print("For more details, see: ARCHITECTURE.md")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
