from config import settings, PROJECT_ROOT
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_community.document_loaders import PyMuPDFLoader 
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import CrossEncoderReranker
from langchain_classic.retrievers import ContextualCompressionRetriever
import os,logging
logger = logging.getLogger("token")

CHROMA_PATH = os.path.join(PROJECT_ROOT, "storage", "chroma_db")

_embeddings = HuggingFaceEmbeddings(model_name=settings.embedder)
_splitter = RecursiveCharacterTextSplitter(chunk_size=1200,chunk_overlap=200)
_vectorstore = Chroma(collection_name="document",embedding_function=_embeddings,persist_directory=CHROMA_PATH)
_reranker_model = HuggingFaceCrossEncoder(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
_reranker = CrossEncoderReranker(model=_reranker_model, top_n=3)

def index_doc(file_path,doc_id):
    loader = PyMuPDFLoader(file_path)
    pages= loader.load()
    full_chunks=[]
    chunk_index=0
    for page in pages:
        page_number = page.metadata.get("page",0)+1
        chunks = _splitter.split_text(page.page_content)
        for chunk in chunks:
            full_chunks.append(
                Document(page_content=chunk, 
                    metadata={"doc_id": doc_id,"chunk_index": chunk_index,
                              "page":page_number,"source":file_path}))
            chunk_index += 1
            
    ids = [f"{doc_id}_{i}" for i in range(len(full_chunks))]
    _vectorstore.add_documents(full_chunks,ids=ids)
    return len(full_chunks)

def search_doc(query,doc_id,top_k=3,rerank=10):
    search_kwargs={'k':rerank}
    if doc_id:
        search_kwargs['filter']={'doc_id':doc_id}
    
    base_retriever =_vectorstore.as_retriever(search_kwargs=search_kwargs)
    compress_retriever = ContextualCompressionRetriever(
        base_compressor=_reranker,
        base_retriever=base_retriever
    )
    results = compress_retriever.invoke(query)
    
    return [
        {"text": doc.page_content, "chunk_index": doc.metadata.get("chunk_index"), "page": doc.metadata.get("page")}
        for doc in results[:top_k]
    ]


def search_all_doc(query,top_k=3,rerank=10):
    base_retriever= _vectorstore.as_retriever(search_kwargs={'k':rerank})
    compress_retriever = ContextualCompressionRetriever(
        base_compressor=_reranker,
        base_retriever=base_retriever
    )
    results = compress_retriever.invoke(query)
    return [
       {
           'text' : doc.page_content,
           'doc_id': doc.metadata.get("doc_id"),
           'page': doc.metadata.get("page"),
           'source': doc.metadata.get("source"),
       }
       for doc in results[:top_k]
    ]
    
    
def index_folder(folder_path):
    results = {}
    if not os.path.isdir(folder_path):
        raise ValueError(f"Not a directory: {folder_path}")
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
    
    if not pdf_files:
        return {}
    
    for filename in pdf_files:
        file_path = os.path.join(folder_path, filename)
        doc_id = os.path.splitext(filename)[0]
        try:
            chunks = index_doc(file_path, doc_id)
            results[doc_id] = chunks
            logger.info(f"Indexed {doc_id} | {chunks} chunks")
        except Exception as e:
            logger.error(f"Failed to index {filename}: {e}")
            results[doc_id] = 0
    
    return results