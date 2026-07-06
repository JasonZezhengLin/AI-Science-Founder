import os
import requests
import time
import warnings
from typing import Dict, List, Optional, Union

import backoff

from ai_scientist.tools.base_tool import BaseTool


def on_backoff(details: Dict) -> None:
    print(
        f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
        f"calling function {details['target'].__name__} at {time.strftime('%X')}"
    )


class SemanticScholarSearchTool(BaseTool):
    def __init__(
        self,
        name: str = "SearchSemanticScholar",
        description: str = (
            "Search for relevant literature using Semantic Scholar. "
            "Provide a search query to find relevant papers."
        ),
        max_results: int = 10,
    ):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers.",
            }
        ]
        super().__init__(name, description, parameters)
        self.max_results = max_results
        self.S2_API_KEY = os.getenv("S2_API_KEY")
        if not self.S2_API_KEY:
            warnings.warn(
                "No Semantic Scholar API key found. Requests will be subject to stricter rate limits. "
                "Set the S2_API_KEY environment variable for higher limits."
            )

    def use_tool(self, query: str) -> Optional[str]:
        # cross-founder visibility gate: the ecosystem-internal peer block is a
        # second peer-injection channel (besides founder_shell._peer_papers_brief).
        # When CROSS_FOUNDER_VISIBILITY is off we suppress ONLY the internal
        # ecosystem peers; external Semantic Scholar results stay in both arms so
        # the NO-PEER control isolates "seeing peers" as the single varied factor.
        import os
        peer_visible = os.environ.get("CROSS_FOUNDER_VISIBILITY", "0") not in (
            "0", "false", "False", "",
        )

        # Stage-3 A2: channel-B self-exclusion. In Stage-1/2 channel B (this
        # internal ecosystem block) did NOT exclude the calling founder's own
        # papers, so a PEER founder re-saw their own work here even though
        # channel A (_peer_papers_brief) already excluded self. When
        # CHANNEL_B_EXCLUDE_FOUNDER is set to a founder_id, we pass it through to
        # search() so channel B also shows only *other* founders' papers. Unset
        # (Stage-1/2 default) preserves the original include-self behaviour.
        exclude_founder = os.environ.get("CHANNEL_B_EXCLUDE_FOUNDER") or None

        internal_papers = []
        if peer_visible:
            try:
                from ai_system.literature_db import get_literature_db

                internal_papers = get_literature_db().search(
                    query, top_k=self.max_results, exclude_founder=exclude_founder
                )
            except Exception:
                pass

        external_papers = None
        try:
            external_papers = self.search_for_papers(query)
        except Exception as e:
            print(f"Semantic Scholar search failed (continuing with internal only): {e}")

        parts = ["=== Previous Work (Semantic Scholar) ==="]
        if external_papers:
            parts.append(self.format_papers(external_papers))
        else:
            parts.append("No results found.")

        if peer_visible:
            parts.append("\n=== Latest Work from Peers in the Ecosystem (Internal Database) ===")
            if internal_papers:
                parts.append(self._format_internal_papers(internal_papers))
            else:
                parts.append("No results found.")
        return "\n".join(parts)

    def _format_internal_papers(self, papers: List[Dict]) -> str:
        paper_strings = []
        for i, paper in enumerate(papers):
            authors = ", ".join(paper.get("authors", []))
            status = paper.get("status", "unknown")
            if status == "published":
                status_label = "Published (peer-reviewed)"
            elif status == "under_review":
                status_label = "Under review inside ecosystem"
            elif status == "rejected":
                status_label = "Rejected inside ecosystem"
            else:
                status_label = status
            paper_strings.append(
                f"{i + 1}: {paper.get('title', 'Unknown Title')}. {authors}. Ecosystem.\n"
                f"   Status: {status_label}\n"
                f"   Abstract: {paper.get('abstract', 'No abstract available.')}\n"
                f"   Founder: {paper.get('founder_id', 'unknown')}\n"
                f"   PDF: {paper.get('pdf_path', 'N/A')}"
            )
        return "\n\n".join(paper_strings)

    @backoff.on_exception(
        backoff.expo,
        (
            requests.exceptions.HTTPError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ),
        on_backoff=on_backoff,
        max_tries=3,
        max_time=15,
    )
    def search_for_papers(self, query: str) -> Optional[List[Dict]]:
        if not query:
            return None
        
        headers = {}
        if self.S2_API_KEY:
            headers["X-API-KEY"] = self.S2_API_KEY
        
        rsp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers=headers,
            params={
                "query": query,
                "limit": self.max_results,
                "fields": "title,authors,venue,year,abstract,citationCount",
            },
            timeout=10,
        )
        print(f"Response Status Code: {rsp.status_code}")
        print(f"Response Content: {rsp.text[:500]}")
        rsp.raise_for_status()
        results = rsp.json()
        total = results.get("total", 0)
        if total == 0:
            return None

        papers = results.get("data", [])
        # Sort papers by citationCount in descending order
        papers.sort(key=lambda x: x.get("citationCount", 0), reverse=True)
        return papers

    def format_papers(self, papers: List[Dict]) -> str:
        paper_strings = []
        for i, paper in enumerate(papers):
            authors = ", ".join(
                [author.get("name", "Unknown") for author in paper.get("authors", [])]
            )
            paper_strings.append(
                f"""{i + 1}: {paper.get("title", "Unknown Title")}. {authors}. {paper.get("venue", "Unknown Venue")}, {paper.get("year", "Unknown Year")}.
Number of citations: {paper.get("citationCount", "N/A")}
Abstract: {paper.get("abstract", "No abstract available.")}"""
            )
        return "\n\n".join(paper_strings)


@backoff.on_exception(
    backoff.expo,
    (
        requests.exceptions.HTTPError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    ),
    on_backoff=on_backoff,
    max_tries=3,
    max_time=15,
)
def search_for_papers(query, result_limit=10) -> Union[None, List[Dict]]:
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {}
    if not S2_API_KEY:
        warnings.warn(
            "No Semantic Scholar API key found. Requests will be subject to stricter rate limits."
        )
    else:
        headers["X-API-KEY"] = S2_API_KEY
    
    if not query:
        return None
    
    rsp = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        headers=headers,
        params={
            "query": query,
            "limit": result_limit,
            "fields": "title,authors,venue,year,abstract,citationStyles,citationCount",
        },
        timeout=10,
    )
    print(f"Response Status Code: {rsp.status_code}")
    print(
        f"Response Content: {rsp.text[:500]}"
    )  # Print the first 500 characters of the response content
    rsp.raise_for_status()
    results = rsp.json()
    total = results["total"]
    time.sleep(1.0)
    if not total:
        return None

    papers = results["data"]
    return papers
