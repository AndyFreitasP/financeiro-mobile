import flet as ft
import sqlite3
from datetime import datetime
from fpdf import FPDF
import os
import re
import json
import warnings
import logging
from dotenv import load_dotenv
import urllib.parse

# --- IMPORTAÇÃO DO SDK OFICIAL ---
import google.generativeai as genai 

# ==============================================================================
# 0. CONFIGURAÇÃO DE AMBIENTE E PERSISTÊNCIA ANDROID
# ==============================================================================
load_dotenv()
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")
logging.getLogger("flet").setLevel(logging.ERROR)

try:
    caminho_raiz = os.getcwd()
    DB_NAME = os.path.join(caminho_raiz, "dados_financeiros.db")
    PASTA_COMPROVANTES = os.path.join(caminho_raiz, "comprovantes")
    if not os.path.exists(PASTA_COMPROVANTES):
        os.makedirs(PASTA_COMPROVANTES)
except Exception as e:
    DB_NAME = "dados_financeiros.db"

# ==============================================================================
# 1. CÉREBRO DA AUTIAH (CONTEXTUAL)
# ==============================================================================
API_KEY = os.getenv("API_KEY")
TEM_IA = bool(API_KEY)

if TEM_IA:
    try:
        genai.configure(api_key=API_KEY)
    except Exception as e:
        print(f"Erro config Autiah: {e}")
        TEM_IA = False

def chamar_autiah(prompt: str, temperatura=0.3) -> str | None:
    if not TEM_IA: return None
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            prompt,
            generation_config={"temperature": temperatura, "max_output_tokens": 400}
        )
        if response and response.text: return response.text.strip()
    except Exception as e:
        print("Erro Autiah:", e)
    return None

# ==============================================================================
# 2. SISTEMA (DB + HELPERS)
# ==============================================================================
def conectar_bd():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS lembretes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, data_vencimento TEXT, valor REAL, status TEXT DEFAULT 'Pendente', anexo TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS perfil (id INTEGER PRIMARY KEY, tipo TEXT UNIQUE, valor REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS assinaturas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, em_uso INTEGER DEFAULT 1)")
    conn.commit()
    return conn, cursor

conn, cursor = conectar_bd()

def limpar_valor(texto):
    if not texto: return 0.0
    try:
        texto_limpo = re.sub(r'[^\d.,]', '', str(texto))
        if ',' in texto_limpo and '.' in texto_limpo: 
            texto_limpo = texto_limpo.replace('.', '').replace(',', '.')
        elif ',' in texto_limpo:
            texto_limpo = texto_limpo.replace(',', '.')
        return float(texto_limpo)
    except: return 0.0

def formatar_moeda_visual(valor_float):
    return f"R$ {valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- LEITURA DE DADOS ---
def adicionar(data, desc, cat, tipo, valor):
    v = abs(valor) * -1 if tipo == "Despesa" else abs(valor)
    cursor.execute("INSERT INTO financeiro (data, descricao, categoria, tipo, valor) VALUES (?, ?, ?, ?, ?)", (data, desc, cat, tipo, v)); conn.commit()

def listar(mes_filtro=None):
    sql = "SELECT * FROM financeiro"; p = []
    if mes_filtro: sql += " WHERE data LIKE ?"; p.append(f"%/{mes_filtro}")
    sql += " ORDER BY id DESC"; cursor.execute(sql, p); return cursor.fetchall()

def listar_recentes(limite=5):
    cursor.execute("SELECT data, descricao, valor FROM financeiro ORDER BY id DESC LIMIT ?", (limite,))
    return cursor.fetchall()

def deletar(idr): cursor.execute("DELETE FROM financeiro WHERE id = ?", (idr,)); conn.commit()

def get_meses():
    m = set(); cursor.execute("SELECT data FROM financeiro")
    for r in cursor:
        try: m.add((datetime.strptime(r[0], "%d/%m/%Y").year, datetime.strptime(r[0], "%d/%m/%Y").month))
        except: continue
    now = datetime.now(); m.add((now.year, now.month)); return [f"{mm:02d}/{y}" for y, mm in sorted(list(m))]

def criar_lembrete(n, d, v): cursor.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status) VALUES (?, ?, ?, 'Pendente')", (n, d, v)); conn.commit()
def set_renda(valor): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (valor,)); conn.commit()
def get_renda(): cursor.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = cursor.fetchone(); return res[0] if res else 0.0
def set_intro_ok(): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); conn.commit()
def reset_intro(): cursor.execute("DELETE FROM perfil WHERE tipo='intro_ok'"); conn.commit() # RESET PARA TESTES
def is_intro_ok(): cursor.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = cursor.fetchone(); return True if res and res[0] == 1 else False
def adicionar_assinatura(nome, valor): cursor.execute("INSERT INTO assinaturas (nome, valor, em_uso) VALUES (?, ?, 1)", (nome, valor)); conn.commit()
def listar_assinaturas(): cursor.execute("SELECT * FROM assinaturas"); return cursor.fetchall()
def toggle_uso_assinatura(id_ass, status_atual): 
    novo = 0 if status_atual == 1 else 1
    cursor.execute("UPDATE assinaturas SET em_uso = ? WHERE id = ?", (novo, id_ass)); conn.commit()
def deletar_assinatura(id_ass): cursor.execute("DELETE FROM assinaturas WHERE id = ?", (id_ass,)); conn.commit()

# --- INTELIGÊNCIA ---
def interpretar_comando(texto):
    if not TEM_IA: return None
    try:
        prompt = f"""Extraia dados JSON. Hoje: {datetime.now().strftime('%d/%m/%Y')}.
        Texto: "{texto}". Saída JSON: {{"nome": "str", "valor": float, "data": "dd/mm/aaaa"}}."""
        txt = chamar_autiah(prompt, temperatura=0.1)
        if not txt: return None
        txt = txt.replace("```json", "").replace("```", "").strip()
        if "{" not in txt: return None
        return json.loads(txt)
    except: return None

def gerar_contexto_completo():
    renda = get_renda()
    cursor.execute("SELECT SUM(valor) FROM financeiro"); saldo = cursor.fetchone()[0] or 0
    recentes = listar_recentes(5)
    txt_recentes = "\n".join([f"- {r[0]}: {r[1]} ({formatar_moeda_visual(r[2])})" for r in recentes])
    
    return f"""
    VOCÊ É A AUTIAH. Parceira financeira do usuário.
    CONTEXTO ATUAL:
    - Renda Mensal: {formatar_moeda_visual(renda)}
    - Saldo Total: {formatar_moeda_visual(saldo)}
    - Últimas Movimentações:
    {txt_recentes}
    Seja literal e direta.
    """

# ==============================================================================
# 3. INTERFACE (V53 - ÍCONE PIX CORRIGIDO)
# ==============================================================================
class RelatorioPDF(FPDF):
    def header(self):
        self.set_fill_color(255, 255, 255); self.rect(0, 0, 210, 297, 'F')
        self.set_fill_color(14, 165, 233); self.rect(0, 0, 210, 30, 'F'); self.set_y(8)
        self.set_font('Arial', 'B', 18); self.set_text_color(255, 255, 255)
        self.cell(0, 10, "FINANTEA - Extrato", 0, 1, 'C'); self.ln(15)

def gerar_pdf(dados, mes):
    try:
        nome = f"extrato_{mes.replace('/','_')}.pdf"
        caminho_final = os.path.join(PASTA_COMPROVANTES, nome) if 'PASTA_COMPROVANTES' in globals() else nome
        pdf = RelatorioPDF(); pdf.add_page(); pdf.set_text_color(0); pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, f"Referencia: {mes}", ln=True); pdf.ln(2)
        pdf.set_fill_color(240); pdf.set_font("Arial", "B", 10)
        pdf.cell(30, 10, "Data", 1, 0, 'C', 1); pdf.cell(110, 10, "Descricao", 1, 0, 'L', 1); pdf.cell(40, 10, "Valor", 1, 1, 'R', 1)
        pdf.set_font("Arial", "", 10)
        for r in dados:
            pdf.ln(); pdf.cell(30, 8, r[1], 1, 0, 'C'); pdf.cell(110, 8, f" {r[2][:50]}", 1, 0, 'L')
            if r[5]<0: pdf.set_font("Arial", "B", 10)
            else: pdf.set_font("Arial", "", 10)
            pdf.cell(40, 8, f"{r[5]:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 1, 1, 'R'); pdf.set_font("Arial", "", 10)
        pdf.output(caminho_final)
        return caminho_final
    except: return None

def main(page: ft.Page):
    page.title = "Finantea"
    page.theme_mode = "dark"
    page.bgcolor = "#0f172a"
    page.padding = 0 
    COR_PRINCIPAL = "#0ea5e9"

    def notificar(msg, cor="green"):
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=cor); page.snack_bar.open=True; page.update()

    def mascara_dinheiro(e):
        v = "".join(filter(str.isdigit, e.control.value))
        if not v: e.control.value = ""
        else: e.control.value = f"R$ {int(v)/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        e.control.update()

    def barra_simbolos():
        return ft.Container(content=ft.Row([
            ft.Tooltip(message="Autismo", content=ft.Icon(ft.icons.EXTENSION, color="#007ACC")),
            ft.Tooltip(message="Deficiências Ocultas", content=ft.Icon(ft.icons.WB_SUNNY, color="#fbbf24")),
            ft.Tooltip(message="Neurodiversidade", content=ft.Icon(ft.icons.ALL_INCLUSIVE, color="red")),
        ], alignment="center", spacing=20), padding=20)

    # --- NAVEGAÇÃO ---
    conteudo = ft.Container(expand=True)

    def mudar(idx):
        if idx == 0: conteudo.content = tela_extrato()
        elif idx == 1: conteudo.content = tela_ferramentas()
        elif idx == 2: conteudo.content = tela_assinaturas()
        page.update()

    # --- TELA 0: ONBOARDING ---
    def tela_onboarding():
        t_renda = ft.TextField(label="Qual sua Renda Mensal?", prefix_text="R$ ", keyboard_type="number", on_change=mascara_dinheiro, text_size=20, width=300)
        
        def acao_comecar(e):
            val = limpar_valor(t_renda.value)
            if val <= 0: notificar("Digite um valor válido.", "red"); return
            set_renda(val); set_intro_ok(); notificar("Perfil Criado!"); mudar(0)
        
        def acao_pular(e): 
            set_intro_ok()
            notificar("Adicione sua renda depois em Ferramentas.", "#fbbf24") 
            mudar(0)

        return ft.Container(alignment=ft.alignment.center, content=ft.Column([
            ft.Icon("rocket_launch", size=60, color=COR_PRINCIPAL),
            ft.Text("Bem-vindo ao Finantea!", size=24, weight="bold"),
            ft.Text("Comece agora a gerenciar sua renda", size=16, color="grey"),
            ft.Container(height=20),
            t_renda,
            ft.ElevatedButton("Iniciar", bgcolor=COR_PRINCIPAL, color="white", width=200, height=50, on_click=acao_comecar),
            ft.TextButton("Pular por enquanto", on_click=acao_pular),
            ft.Container(height=30), barra_simbolos()
        ], alignment="center", horizontal_alignment="center"))

    # TELA 1: EXTRATO
    def tela_extrato():
        lista = ft.Column(scroll="auto", expand=True)
        t_data = ft.TextField(label="Quando?", value=datetime.now().strftime("%d/%m/%Y"), width=100)
        t_desc = ft.TextField(label="Com o que?", expand=True)
        t_val = ft.TextField(label="Quanto?", width=150, keyboard_type="number", on_change=mascara_dinheiro)
        t_tipo = ft.Dropdown(width=100, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")
        
        txt_ganhou = ft.Text("Ent: R$ 0,00", color="#4ade80")
        txt_gastou = ft.Text("Sai: R$ 0,00", color="#f87171")
        txt_saldo = ft.Text("R$ 0,00", size=20, weight="bold")
        
        meses = get_meses(); mes_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
        if mes_atual not in meses: meses.append(mes_atual)
        dd_mes = ft.Dropdown(options=[ft.dropdown.Option(m) for m in meses], value=mes_atual)

        def render():
            dados = listar(dd_mes.value)
            ent = sum(r[5] for r in dados if r[5]>0); sai = abs(sum(r[5] for r in dados if r[5]<0)); bal = ent-sai
            txt_ganhou.value = f"Ent: {formatar_moeda_visual(ent)}"
            txt_gastou.value = f"Sai: {formatar_moeda_visual(sai)}"
            txt_saldo.value = f"Saldo: {formatar_moeda_visual(bal)}"
            txt_saldo.color = "#4ade80" if bal >= 0 else "#f87171"
            lista.controls.clear()
            for r in dados:
                cor = "#f87171" if r[5]<0 else "#4ade80"
                btn = ft.IconButton(icon="delete", icon_color="grey", on_click=lambda e, x=r[0]: (deletar(x), render(), page.update()))
                lista.controls.append(ft.Container(content=ft.Row([ft.Text(r[1], width=80), ft.Text(r[2], expand=True), ft.Text(f"R$ {r[5]:.2f}", color=cor), btn]), bgcolor="#1e293b", padding=10, border_radius=5, border=ft.border.only(left=ft.border.BorderSide(4, cor))))
            page.update()

        def salvar(e):
            val = limpar_valor(t_val.value)
            if val == 0: notificar("Valor zero.", "red"); return
            adicionar(t_data.value, t_desc.value, "Geral", t_tipo.value, val)
            t_desc.value=""; t_val.value=""; notificar("Salvo!"); render()

        def criar_pdf(e):
            d = listar(dd_mes.value)
            if not d: notificar("Vazio.", "red"); return
            arq = gerar_pdf(d, dd_mes.value)
            if arq: notificar(f"PDF Salvo!"); 
            try: page.launch_url(arq) 
            except: pass

        dd_mes.on_change = lambda e: render()
        btn_add = ft.ElevatedButton("Salvar", bgcolor=COR_PRINCIPAL, color="white", on_click=salvar)
        btn_pdf = ft.IconButton(icon="picture_as_pdf", icon_color=COR_PRINCIPAL, on_click=criar_pdf)
        render()
        return ft.Container(padding=10, content=ft.Column([
            ft.Row([ft.Text("Extrato", size=24, weight="bold"), ft.Row([dd_mes, btn_pdf], spacing=10)], alignment="spaceBetween"),
            ft.Container(content=ft.Column([ft.Row([txt_ganhou, txt_gastou], alignment="spaceBetween"), ft.Divider(), ft.Row([txt_saldo], alignment="center")]), bgcolor="#1e293b", padding=15, border_radius=10),
            lista,
            ft.Container(content=ft.Column([ft.Row([t_data, t_tipo, t_val]), ft.Row([t_desc]), btn_add]), bgcolor="#1e293b", padding=15, border_radius=10)
        ], expand=True))

    # TELA 2: FERRAMENTAS
    def tela_ferramentas():
        t_renda = ft.TextField(label="Sua Renda Mensal", value=formatar_moeda_visual(get_renda()), width=180, on_change=mascara_dinheiro)
        def salvar_renda(e): set_renda(limpar_valor(t_renda.value)); notificar("Renda salva!"); tela_ferramentas()
        box_renda = ft.Container(content=ft.Row([t_renda, ft.IconButton(icon="save", on_click=salvar_renda, icon_color=COR_PRINCIPAL)]), bgcolor="#1e293b", padding=10, border_radius=10)

        t_dica = ft.Text("Dica da Autiah", weight="bold", color=COR_PRINCIPAL); c_dica = ft.Text("Toque na mágica...", size=12)
        def carregar_dica(e): 
            t_dica.value = "Analisando..."; page.update()
            ctx = gerar_contexto_completo() + "\nTarefa: Dê uma dica curta."
            txt = chamar_autiah(ctx)
            t_dica.value, c_dica.value = "Dica da Autiah:", txt if txt else "Erro."
            page.update()
        box_ia = ft.Container(content=ft.Column([ft.Row([t_dica, ft.IconButton(icon="auto_awesome", icon_color=COR_PRINCIPAL, on_click=carregar_dica)], alignment="spaceBetween"), c_dica]), bgcolor="#1e293b", padding=15, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, COR_PRINCIPAL)))

        renda = get_renda(); hora = renda/160 if renda>0 else 0
        t_preco = ft.TextField(label="Preço", prefix_text="R$ ", on_change=mascara_dinheiro, expand=True); l_vida = ft.Text("Custará x horas de vida", italic=True)
        def calc_vida(e): v=limpar_valor(t_preco.value); l_vida.value = f"Custo: {v/hora:.1f} horas de trabalho" if hora>0 else "Defina sua renda!"
        box_vida = ft.Container(content=ft.Column([ft.Text("Preço de Vida", weight="bold"), ft.Row([t_preco, ft.IconButton(icon="calculate", on_click=lambda e: (calc_vida(e), page.update()))]), l_vida]), bgcolor="#1e293b", padding=10, border_radius=10)

        t_tot = ft.TextField(label="Total", width=100, on_change=mascara_dinheiro); t_pag = ft.TextField(label="Pago", width=100, on_change=mascara_dinheiro); l_troco = ft.Text("Troco: R$ 0,00", weight="bold")
        def calc_troco(e): l_troco.value = f"Troco: {formatar_moeda_visual(limpar_valor(t_pag.value) - limpar_valor(t_tot.value))}"; page.update()
        box_troco = ft.Container(content=ft.Column([ft.Text("Troco"), ft.Row([t_tot, t_pag, ft.IconButton(icon="calculate", on_click=calc_troco)]), l_troco]), bgcolor="#1e293b", padding=10, border_radius=10)

        t_chat = ft.TextField(label="Fale com a Autiah", expand=True); l_resp = ft.Text("")
        def enviar_chat(e):
            if not TEM_IA: l_resp.value = "Offline."; return
            l_resp.value = "Pensando..."; page.update()
            ctx = gerar_contexto_completo() + f"\nPERGUNTA: {t_chat.value}"
            l_resp.value = chamar_autiah(ctx) or "Erro."; page.update()
        box_chat = ft.Container(content=ft.Column([ft.Text("Chat Contextual", weight="bold"), ft.Row([t_chat, ft.IconButton(icon="send", on_click=enviar_chat)]), l_resp]), bgcolor="#1e293b", padding=10, border_radius=10)

        # ICONE CORRIGIDO AQUI: ft.icons.QR_CODE no lugar de PIX
        def copiar_pix(e): page.set_clipboard("85996994887"); notificar("Pix copiado!", "#32bcad")
        box_pix = ft.Container(content=ft.Row([ft.Icon(ft.icons.QR_CODE, color="#32bcad"), ft.Column([ft.Text("Minha Chave Pix", weight="bold"), ft.Text("85996994887", size=12)]), ft.IconButton(icon="content_copy", on_click=copiar_pix)]), bgcolor="#1e293b", padding=10, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, "#32bcad")))

        # BOTÃO DE RESET PARA TESTES
        def acao_reset(e): reset_intro(); notificar("App resetado! Reinicie o app.", "red")
        btn_reset = ft.TextButton("Resetar Introdução (Teste)", on_click=acao_reset)

        return ft.Container(padding=10, content=ft.Column([
            ft.Text("Ferramentas", size=24, weight="bold"),
            box_renda, ft.Container(height=10),
            box_ia, ft.Container(height=10),
            box_vida, ft.Container(height=10),
            box_chat, ft.Container(height=10),
            box_troco, ft.Container(height=10),
            box_pix, ft.Container(height=10),
            btn_reset # BOTÃO ADICIONADO
        ], scroll="auto"), expand=True)

    # TELA 3: ASSINATURAS
    def tela_assinaturas():
        lista_ass = ft.Column(expand=True, scroll="auto")
        t_nome = ft.TextField(label="Nome", expand=True); t_valor = ft.TextField(label="Valor", width=100, on_change=mascara_dinheiro)
        def render():
            lista_ass.controls.clear(); ass = listar_assinaturas()
            lista_ass.controls.append(ft.Container(content=ft.Text(f"Total: {formatar_moeda_visual(sum(a[2] for a in ass))}", weight="bold"), bgcolor="#334155", padding=5))
            for a in ass:
                cor = "#4ade80" if a[3] else "#f87171"
                lista_ass.controls.append(ft.Container(content=ft.Row([
                    ft.Text(a[1], expand=True), ft.Text(formatar_moeda_visual(a[2])),
                    ft.IconButton(icon=ft.icons.THUMB_UP if a[3] else ft.icons.THUMB_DOWN, icon_color=cor, on_click=lambda e, x=a[0], s=a[3]: (toggle_uso_assinatura(x, s), render(), page.update())),
                    ft.IconButton(icon="delete", on_click=lambda e, x=a[0]: (deletar_assinatura(x), render(), page.update()))
                ]), bgcolor="#1e293b", padding=5, border_radius=5, border=ft.border.only(left=ft.border.BorderSide(4, cor))))
        def add(e): adicionar_assinatura(t_nome.value, limpar_valor(t_valor.value)); t_nome.value=""; t_valor.value=""; render(); page.update()
        render()
        return ft.Container(padding=10, content=ft.Column([ft.Text("Assinaturas", size=22, weight="bold"), lista_ass, ft.Row([t_nome, t_valor, ft.IconButton(icon="add", on_click=add)])], expand=True))

    # --- MENU PRINCIPAL ---
    def navegar(e):
        idx = e.control.selected_index
        if idx == 3: 
            page.set_clipboard("85996994887")
            notificar("Pix copiado!", "#32bcad")
            page.drawer.open = False; page.update(); return
        mudar(idx); page.drawer.open = False; page.update()

    page.drawer = ft.NavigationDrawer(bgcolor="#1e293b", indicator_color=COR_PRINCIPAL, controls=[
        ft.NavigationDrawerDestination(label="Extrato", icon=ft.icons.LIST),               
        ft.NavigationDrawerDestination(label="Ferramentas", icon=ft.icons.CALCULATE),      
        ft.NavigationDrawerDestination(label="Assinaturas", icon=ft.icons.SUBSCRIPTIONS),  
        ft.NavigationDrawerDestination(label="Doar Café", icon_content=ft.Icon(ft.icons.COFFEE, color="#fbbf24")),
    ], on_change=navegar)

    def abrir_menu(e): page.drawer.open = True; page.update()
    page.appbar = ft.AppBar(leading=ft.IconButton(icon="menu", on_click=abrir_menu), title=ft.Text("Finantea"), bgcolor="#0f172a", elevation=0)
    
    page.add(ft.SafeArea(conteudo, expand=True))
    if not is_intro_ok(): conteudo.content = tela_onboarding()
    else: conteudo.content = tela_extrato()
    page.update()

if __name__ == "__main__":
    ft.app(target=main)
