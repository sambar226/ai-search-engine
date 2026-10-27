import asyncio
import httpx
from bs4 import BeautifulSoup
import redis.asyncio as redis
from redis.exceptions import ResponseError
from urllib.parse import urljoin,urlparse

# Redis connection (Ensure Redis is running with the RedisBloom module)
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

FRONTIER_KEY = "url_frontier"
BLOOM_FILTER_KEY = "seen_urls"
#SEED_URL = "https://example-domain.com"
#ALLOWED_DOMAIN = "example-domain.com"
#MAX_PAGES = 50
SEED_URL = "http://quotes.toscrape.com/"
ALLOWED_DOMAIN = "quotes.toscrape.com"
MAX_PAGES = 5  # Keep it small for a quick test

async def setup_redis():
    """ Initialize bloom filter and seed the URL frontier """

    try:
        await redis_client.bf().create(BLOOM_FILTER_KEY,0.1,10000)

    except ResponseError:
        pass

    await redis_client.lpush(FRONTIER_KEY,SEED_URL)

async def extract_links_and_text(html,base_url):
    soup=BeautifulSoup(html,"html.parser")
    text=soup.get_text(separator=' ',strip=True)

    links=[]
    for a_tag in soup.find_all('a', href=True):
        full_url=urljoin(base_url, a_tag['href'])
        if urlparse(full_url).netloc== ALLOWED_DOMAIN:
            links.append(full_url)
    return text, links

async def crawl_worker(worker_id):
    async with httpx.AsyncClient() as client:
        pages_crawled=0
        while pages_crawled < MAX_PAGES:
            url = await redis_client.rpop(FRONTIER_KEY)
            if not url:
                await asyncio.sleep(1)
                continue

            # Check Bloom filter to see if URL was already processed
            is_seen= await redis_client.bf().exists(BLOOM_FILTER_KEY, url)
            if is_seen:
                continue

            print(f"[Worker {worker_id}] Crawling: {url}")
            try:
                response= await client.get(url, timeout=5.0, follow_redirects=True)
                if response.status_code==200:
                    text, links= await extract_links_and_text(response.text, url)

                    # Mark as seen in bloom filter
                    await redis_client.bf().add(BLOOM_FILTER_KEY, url)

                    for link in links:
                        await redis_client.lpush(FRONTIER_KEY, link)

                    # Send text to a local file or directly to the indexer queue
                    with open("crawled_data.txt","a",encoding="utf-8") as f:
                        f.write(f"URL:{url}/nCONTENT:{text[:1000]}....\n---\n")

                    pages_crawled+=1
                else: 
                    print(f"[Worker {worker_id}] Skipped {url} (Status: {response.status_code})")
            except Exception as e:
                print(f"[Worker {worker_id}] Failed {url}: {e}")

                # Per-domain politeness delay
            await asyncio.sleep(2)


async def main():
    await setup_redis()
    # Run multiple workers for concurrent crawling
    workers = [crawl_worker(i) for i in range(3)]
    await asyncio.gather(*workers)

if __name__=="__main__":
    asyncio.run(main())