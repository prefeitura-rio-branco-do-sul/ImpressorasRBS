"""Funções puras relacionadas a endereços de rede."""
import ipaddress


def ip_normalizado(ip):
    try:
        return str(ipaddress.ip_address(str(ip or "").strip()))
    except ValueError:
        return ""
