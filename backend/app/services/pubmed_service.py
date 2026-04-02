"""
PubMed Integration — live medical literature search.

Adds a new agent tool that searches PubMed's E-utilities API
when uploaded documents don't have enough information.

Features:
  - Search PubMed for relevant articles
  - Fetch abstracts automatically
  - Format as retrievable chunks with proper citations
  - Agent decides when to use PubMed vs local docs
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional
from xml.etree import ElementTree

import httpx

from app.core.logging import get_logger
from app.services.agent.state import RetrievedChunk

logger = get_logger(__name__)

PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


@dataclass
class PubMedArticle:
    pmid: str
    title: str
    abstract: str
    authors: List[str]
    journal: str
    year: str
    doi: Optional[str] = None


class PubMedService:
    """Searches PubMed and returns article abstracts as retrievable chunks."""

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    async def search(self, query: str, max_results: Optional[int] = None) -> List[PubMedArticle]:
        """Search PubMed and fetch article details."""
        n = max_results or self.max_results

        try:
            # Step 1: Search for PMIDs
            pmids = await self._search_pmids(query, n)
            if not pmids:
                logger.info(f"PubMed: No results for '{query}'")
                return []

            # Step 2: Fetch article details
            articles = await self._fetch_articles(pmids)
            logger.info(f"PubMed: Found {len(articles)} articles for '{query}'")
            return articles

        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return []

    async def _search_pmids(self, query: str, max_results: int) -> List[str]:
        """Search PubMed and return list of PMIDs."""
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "sort": "relevance",
            "retmode": "json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(PUBMED_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        return data.get("esearchresult", {}).get("idlist", [])

    async def _fetch_articles(self, pmids: List[str]) -> List[PubMedArticle]:
        """Fetch article details from PubMed."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(PUBMED_FETCH_URL, params=params)
            resp.raise_for_status()

        return self._parse_xml(resp.text)

    def _parse_xml(self, xml_text: str) -> List[PubMedArticle]:
        """Parse PubMed XML response into PubMedArticle objects."""
        articles = []
        try:
            root = ElementTree.fromstring(xml_text)
            for article_elem in root.findall(".//PubmedArticle"):
                try:
                    medline = article_elem.find(".//MedlineCitation")
                    article = medline.find(".//Article")

                    # PMID
                    pmid = medline.findtext(".//PMID", "")

                    # Title
                    title = article.findtext(".//ArticleTitle", "No title")

                    # Abstract
                    abstract_parts = []
                    abstract_elem = article.find(".//Abstract")
                    if abstract_elem is not None:
                        for text in abstract_elem.findall(".//AbstractText"):
                            label = text.get("Label", "")
                            content = text.text or ""
                            if label:
                                abstract_parts.append(f"{label}: {content}")
                            else:
                                abstract_parts.append(content)
                    abstract = "\n".join(abstract_parts) if abstract_parts else "No abstract available."

                    # Authors
                    authors = []
                    author_list = article.find(".//AuthorList")
                    if author_list is not None:
                        for author in author_list.findall(".//Author"):
                            last = author.findtext("LastName", "")
                            first = author.findtext("ForeName", "")
                            if last:
                                authors.append(f"{last} {first}".strip())

                    # Journal
                    journal = article.findtext(".//Journal/Title", "Unknown Journal")

                    # Year
                    year = article.findtext(".//Journal/JournalIssue/PubDate/Year", "")
                    if not year:
                        year = article.findtext(".//ArticleDate/Year", "Unknown")

                    # DOI
                    doi = None
                    for eid in article.findall(".//ELocationID"):
                        if eid.get("EIdType") == "doi":
                            doi = eid.text

                    articles.append(PubMedArticle(
                        pmid=pmid, title=title, abstract=abstract,
                        authors=authors[:3], journal=journal,
                        year=year, doi=doi,
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse article: {e}")
                    continue

        except ElementTree.ParseError as e:
            logger.error(f"XML parse error: {e}")

        return articles

    def articles_to_chunks(
        self, articles: List[PubMedArticle], start_index: int = 1
    ) -> List[RetrievedChunk]:
        """Convert PubMed articles to RetrievedChunk format for the agent."""
        chunks = []
        for i, article in enumerate(articles):
            author_str = ", ".join(article.authors[:3])
            if len(article.authors) > 3:
                author_str += " et al."

            content = (
                f"Title: {article.title}\n"
                f"Authors: {author_str}\n"
                f"Journal: {article.journal} ({article.year})\n"
                f"PMID: {article.pmid}\n"
                f"{'DOI: ' + article.doi if article.doi else ''}\n\n"
                f"Abstract:\n{article.abstract}"
            )

            chunks.append(RetrievedChunk(
                chunk_id=f"pubmed_{article.pmid}",
                document_id=f"pubmed_{article.pmid}",
                document_filename=f"PubMed:{article.pmid}",
                content=content,
                page_number=None,
                relevance_score=0.7,  # Default high relevance for PubMed results
                citation_index=start_index + i,
            ))

        return chunks


# Singleton
_pubmed_service: Optional[PubMedService] = None


def get_pubmed_service() -> PubMedService:
    global _pubmed_service
    if _pubmed_service is None:
        _pubmed_service = PubMedService()
    return _pubmed_service
