"""Native embedding factory package for core.v2 (core-v2/2b).

Kept import-cheap: the factory and dimension probe live in ``local`` and do all
LlamaIndex/torch imports function-locally. Nothing is imported eagerly here so
``import indexed.core.v2.embedding`` stays free of heavy ML deps.
"""
