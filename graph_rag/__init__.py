"""
FinSentry AI - Graph RAG Package
===================================

Graph-based Retrieval-Augmented Generation for investigation context.

Modules:
    retriever       -- GraphRetriever (extract subgraph context from cases).
    context_builder -- ContextBuilder (format context for SAR generation).
"""

from graph_rag.retriever import GraphRetriever
from graph_rag.context_builder import ContextBuilder

__all__ = ["GraphRetriever", "ContextBuilder"]
