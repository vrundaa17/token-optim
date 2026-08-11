from core.tool_selection import select_relevant_tools
from core.cache import check_cache, store_answer
from core.trim import trim_response
import pytest
from core.cache import _cache_collection

@pytest.fixture(autouse=True)
def clear_cache():
    ids = _cache_collection.get()["ids"]
    if ids:
        _cache_collection.delete(ids=ids)
        
def test_selects_relevant_tool():
    tools = [
        {"function": {"name": "calculator", "description": "Perform mathematical calculations"}},
        {"function": {"name": "translator", "description": "Translate text between languages"}},
        {"function": {"name": "calendar", "description": "Check or schedule calendar events"}},
    ]

    result = select_relevant_tools(tools,"What is 12 divided by 4",top_k=1)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "calculator"
    
    
def test_tool_selector_returns_all_if_fewer_than_top_k():
    tools = [{"function": {"name": "only_one", "description": "Does one thing"}}]
    result = select_relevant_tools(tools, "anything", top_k=3)
    assert len(result) == 1
    
    
def test_trim_response_basic():
    raw = {"current": {"temperature_2m": 28.5, "relative_humidity_2m": 60, "extra_field": "ignored"}}
    field_map = {"temp": "current.temperature_2m", "humidity": "current.relative_humidity_2m"}

    result = trim_response(raw, field_map)

    assert result == {"temp": 28.5, "humidity": 60}
    assert "extra_field" not in result
    
    
def test_trim_response_missing_field_returns_none():
    raw = {"current": {"temperature_2m": 28.5}}
    field_map = {"temp": "current.temperature_2m", "missing": "current.does_not_exist"}

    result = trim_response(raw, field_map)

    assert result["temp"] == 28.5
    assert result["missing"] is None
    
    
def test_cache_miss_then_hit():
    query = "What's the capital of France?"
    answer = "Paris"

    result, _ = check_cache(query)
    assert result is None  

    store_answer(query, answer)

    result2, score2 = check_cache("What is France's capital city?")
    assert result2 == answer
    assert score2 > 0.85
    
    
import fitz, pymupdf
from core.document_search import index_doc, search_doc

def _make_test_pdf(path, text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()

def test_index_and_search_pdf(tmp_path):

    pdf_path = str(tmp_path / "test.pdf")
    _make_test_pdf(pdf_path, "The refund window is 45 days for premium members.")

    num_chunks = index_doc(pdf_path,"test_pdf_1")
    assert num_chunks >= 1

    results = search_doc("what is the refund window", doc_id="test_pdf_1", top_k=3)
    assert "45 days" in results[0]["text"]
    assert results[0]["page"] == 1