import uuid
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from google import genai
from google.genai import types

load_dotenv()

# Setup Qdrant and Gemini
client = QdrantClient(url="http://localhost:6333")
genai_client=genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

COLLECTION_NAME = "answer_engine_index"

def create_collection():
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
        
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
    )
    print(f"Collection '{COLLECTION_NAME}' is ready.")

def chunk_text(text, chunk_size=300):
    words = text.split()
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

def get_embedding(text):
    result = genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return result.embeddings[0].values

def parse_crawled_data(filepath):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split using just the dashes, then strip whitespace
    documents = content.split('---')
    for doc in documents:
        doc = doc.strip()
        if not doc:
            continue
            
        # Safely extract URL and CONTENT regardless of exact line breaks
        if "URL:" in doc and "CONTENT:" in doc:
            try:
                url_part, content_part = doc.split("CONTENT:", 1)
                url = url_part.replace("URL:", "").strip()
                text = content_part.strip()
                yield url, text
            except Exception as e:
                print(f"Could not parse a document block: {e}")

def index_documents():
    create_collection()
    docs_indexed = 0
    
    for url, text in parse_crawled_data("crawled_data.txt"):
        chunks = chunk_text(text)
        points = []
        
        for idx, chunk in enumerate(chunks):
            if len(chunk.strip()) < 10:
                continue
                
            vector = get_embedding(chunk)
            point_id = str(uuid.uuid4())
            
            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload={"url": url, "text": chunk, "chunk_id": idx}
            ))
            
        if points:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )
            print(f"Indexed {len(chunks)} chunks for {url}")
            docs_indexed += 1
            
    print(f"\nSuccessfully indexed {docs_indexed} documents into Qdrant!")

if __name__ == "__main__":
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set.")
    else:
        index_documents()

