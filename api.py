from fastapi import FastAPI, Request
from qdrant_client import QdrantClient
from sse_starlette.sse import EventSourceResponse
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

app=FastAPI()
# Setup Qdrant and Gemini
client= QdrantClient(url="http://localhost:6333")
genai_client=genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

COLLECTION_NAME = "answer_engine_index"

def get_query_embedding(text):
    result = genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return result.embeddings[0].values

#def retrieve_context(vector):
    results=client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=3
    )

    contexts=[]
    for hit in results:
        contexts.append(f"Source: {hit.payload['url']}\nContent: {hit.payload['text']}")
    return "\n\n".join(contexts)

def retrieve_context(vector):
    raw_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=3
    )
    
    # 1. Safely extract the list of points regardless of Qdrant client version
    if isinstance(raw_results, list):
        results = raw_results
    elif hasattr(raw_results, 'points'):
        results = raw_results.points
    elif hasattr(raw_results, 'result'):
        results = raw_results.result
    elif isinstance(raw_results, tuple):
        results = raw_results[0]
    else:
        results = []

    contexts = []
    for hit in results:
        # 2. Extract payload safely (handles objects, dictionaries, and missing data)
        if isinstance(hit, dict):
            payload = hit.get('payload', {})
        elif hasattr(hit, 'payload'):
            payload = hit.payload
        else:
            continue  # Skip if we cannot parse the hit format
            
        url = payload.get('url', 'Unknown Source')
        text = payload.get('text', '')
        
        contexts.append(f"Source: {url}\nContent: {text}")
        
    return "\n\n".join(contexts)

@app.get("/search")
async def search(request: Request, q: str):
    # 1. Embed Query
    query_vector = get_query_embedding(q)
    
    # 2. Retrieve Context
    context = retrieve_context(query_vector)
    
    # 3. Construct Prompt
    prompt = (
        "You are an AI answer engine. Answer the user's question using ONLY the provided context. "
        "Always cite your sources inline (e.g., [1], [2]) based on the provided source URLs.\n\n"
        f"Context:\n{context}\n\nQuestion: {q}"
    )

    # 4. Stream Gemini LLM Response
    async def event_generator():
        response = genai_client.models.generate_content_stream(
             model='gemini-3.5-flash-lite', contents=prompt
        )
        
        for chunk in response:
            if await request.is_disconnected():
                break
            if chunk.text:
                yield {"data": chunk.text}
                await asyncio.sleep(0.01) # Small delay to ensure smooth SSE stream
        
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)