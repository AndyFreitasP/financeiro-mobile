import flet as ft
import sqlite3
from datetime import datetime
from fpdf import FPDF
import os
import re
import json
import urllib.request
import urllib.error
import warnings
import logging

# ==============================================================================
# 0. CONFIGURAÇÃO (SEM BIBLIOTECAS EXTERNAS DE ENV)
# ==============================================================================
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")
logging.getLogger("flet").setLevel(logging.ERROR)

DB_NAME = "dados_financeiros.db"
if not os.path.exists("comprovantes"): os.makedirs("comprovantes")

# --- FUNÇÃO MANUAL PARA LER .ENV NO ANDROID ---
def carregar_env_manual():
    """Lê o arquivo .env sem precisar da biblioteca python-dotenv"""
    try:
        env_path = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha or linha.startswith("#") or "=" not in linha:
                        continue
                    chave, valor = linha.split("=", 1)
                    os.environ[chave] = valor
            print(">>> .env carregado manualmente com sucesso.")
        else:
            print(">>> Arquivo .env não encontrado (Usando variáveis do sistema ou padrão).")
    except Exception as e:
        print(f"Erro ao ler .env: {e}")

# Executa o carregamento manual
carregar_env_manual()

# ... rest of the code ...
