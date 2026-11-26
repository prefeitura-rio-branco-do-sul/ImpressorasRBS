"""Funções puras de segurança."""
import hashlib


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
