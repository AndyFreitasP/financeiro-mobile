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
# CONFIGURAÇÃO GERAL
# ==============================================================================
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")
logging.getLogger("flet").setLevel(logging.ERROR)

# Variáveis Globais
DB_NAME = "dados_financeiros.db"
API_KEY = ""
TEM_IA = False

# ==============================================================================
# 1. FUNÇÕES LÓGICAS (SEM UI)
# ==============================================================================
def carregar_env_manual():
    global API_KEY, TEM_IA
    try:
        env_path = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for linha in f:
                    if "=" in linha and not linha.startswith("#"):
                        k, v = linha.strip().split("=", 1)
                        if k == "API_KEY": API_KEY = v; TEM_IA = True
    except: pass

def conectar_bd():
    # Caminho absoluto para garantir que o Android ache o arquivo
    db_path = os.path.join(os.getcwd(), DB_NAME)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS metas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_alvo REAL, valor_atual REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS lembretes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, data_vencimento TEXT, valor REAL, status TEXT, anexo TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS perfil (id INTEGER PRIMARY KEY, tipo TEXT UNIQUE, valor REAL)")
    conn.commit()
    return conn, cursor

# Inicialização segura
carregar_env_manual()
conn, cursor = conectar_bd()

def chamar_gemini(prompt):
    if not TEM_IA: return None
    modelos = ["gemini-1.5-flash", "gemini-pro"]
    for modelo in modelos:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req) as r:
                res = json.loads(r.read().decode('utf-8'))
                if 'candidates' in res: return res['candidates'][0]['content']['parts'][0]['text']
        except: continue
    return None

def limpar_valor(texto):
    try:
        v = re.sub(r'[^\d.,]', '', str(texto))
        if ',' in v and '.' in v: v = v.replace('.', '').replace(',', '.')
        elif ',' in v: v = v.replace(',', '.')
        return float(v)
    except: return 0.0

def formatar_moeda_visual(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- Helpers de BD ---
def adicionar(data, desc, cat, tipo, valor):
    v = abs(valor) * -1 if tipo == "Despesa" else abs(valor)
    cursor.execute("INSERT INTO financeiro (data, descricao, categoria, tipo, valor) VALUES (?, ?, ?, ?, ?)", (data, desc, cat, tipo, v)); conn.commit()
def listar(mes):
    cursor.execute("SELECT * FROM financeiro WHERE data LIKE ? ORDER BY id DESC", [f"%/{mes}"]); return cursor.fetchall()
def deletar(idr): cursor.execute("DELETE FROM financeiro WHERE id = ?", (idr,)); conn.commit()
def get_meses():
    m = set(); cursor.execute("SELECT data FROM financeiro")
    for r in cursor:
        try: m.add((datetime.strptime(r[0], "%d/%m/%Y").year, datetime.strptime(r[0], "%d/%m/%Y").month))
        except: continue
    now = datetime.now(); m.add((now.year, now.month)); return [f"{mm:02d}/{y}" for y, mm in sorted(list(m))]
# Metas/Outros
def criar_meta(n, a): cursor.execute("INSERT INTO metas (nome, valor_alvo, valor_atual) VALUES (?, ?, 0)", (n, a)); conn.commit()
def atualizar_meta(idm, v): cursor.execute("UPDATE metas SET valor_atual = valor_atual + ? WHERE id = ?", (v, idm)); conn.commit()
def listar_metas(): cursor.execute("SELECT * FROM metas"); return cursor.fetchall()
def deletar_meta(idm): cursor.execute("DELETE FROM metas WHERE id = ?", (idm,)); conn.commit()
def criar_lembrete(n, d, v): cursor.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status) VALUES (?, ?, ?, 'Pendente')", (n, d, v)); conn.commit()
def set_renda(v): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (v,)); conn.commit()
def get_renda(): cursor.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = cursor.fetchone(); return res[0] if res else 0.0
def set_intro_ok(): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); conn.commit()
def is_intro_ok(): cursor.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = cursor.fetchone(); return True if res and res[0] == 1 else False

def interpretar_comando(texto):
    if not TEM_IA: return None
    try:
        t = chamar_gemini(f"Extraia JSON. Hoje: {datetime.now().strftime('%d/%m/%Y')}. Texto: '{texto}'. Retorne: {{'nome': str, 'valor': float, 'data': 'dd/mm/aaaa'}}")
        return json.loads(t.replace("```json", "").replace("```", "").strip()) if t else None
    except: return None

# ==============================================================================
# 2. PDF (SIMPLIFICADO)
# ==============================================================================
class RelatorioPDF(FPDF):
    def header(self):
        self.set_fill_color(255); self.rect(0,0,210,297,'F'); self.set_fill_color(14,165,233); self.rect(0,0,210,30,'F'); self.set_y(8)
        self.set_font('Arial','B',18); self.set_text_color(255); self.cell(0,10,"FINANTEA - Extrato",0,1,'C'); self.ln(15)

def gerar_pdf(dados, mes):
    try:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f"extrato_{mes.replace('/','_')}.pdf")
        pdf = RelatorioPDF(); pdf.add_page(); pdf.set_text_color(0); pdf.set_font("Arial","B",12)
        pdf.cell(0,10,f"Ref: {mes}",ln=True); pdf.ln(2); pdf.set_fill_color(240); pdf.set_font("Arial","B",10)
        pdf.cell(30,10,"Data",1,0,'C',1); pdf.cell(110,10,"Descricao",1,0,'L',1); pdf.cell(40,10,"Valor",1,1,'R',1); pdf.set_font("Arial","",10)
        for r in dados:
            pdf.ln(); pdf.cell(30,8,r[1],1,0,'C'); pdf.cell(110,8,f" {r[2][:50]}",1,0,'L'); pdf.cell(40,8,f"{r[5]:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),1,1,'R')
        pdf.output(path); return path
    except: return None

# ==============================================================================
# 3. INTERFACE (CORREÇÃO DE LAYOUT)
# ==============================================================================
def main(page: ft.Page):
    # Configuração Inicial
    page.title = "Finantea"
    page.theme_mode = "dark"
    page.bgcolor = "#0f172a"
    page.padding = 0
    # Importante: Definimos o scroll na PÁGINA inteira, não nos containers internos
    page.scroll = ft.ScrollMode.AUTO 
    
    COR_PRINCIPAL = "#0ea5e9"

    # Feedback Visual de Carregamento
    lbl_loading = ft.Text("Carregando Finantea...", color="white", size=20)
    page.add(ft.Container(content=lbl_loading, alignment=ft.alignment.center, padding=50))
    
    def notificar(msg, cor="green"):
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=cor)
        page.snack_bar.open = True
        page.update()

    def mascara_dinheiro(e):
        v = "".join(filter(str.isdigit, e.control.value))
        e.control.value = f"R$ {int(v)/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if v else ""
        e.control.update()

    # Container Principal (Substituirá o Loading)
    conteudo = ft.Container()

    # --- TELAS ---
    def tela_onboarding():
        t_renda = ft.TextField(label="Renda Mensal", prefix_text="R$ ", keyboard_type="number", on_change=mascara_dinheiro, width=300)
        def ir(e):
            if limpar_valor(t_renda.value) > 0: set_renda(limpar_valor(t_renda.value)); set_intro_ok(); mudar(0)
        return ft.Container(padding=20, content=ft.Column([
            ft.Icon("rocket_launch", size=60, color=COR_PRINCIPAL),
            ft.Text("Bem-vindo!", size=24, weight="bold"),
            t_renda,
            ft.ElevatedButton("Iniciar", bgcolor=COR_PRINCIPAL, color="white", on_click=ir)
        ], horizontal_alignment="center"))

    def tela_extrato():
        # Elementos UI
        t_data = ft.TextField(label="Data", value=datetime.now().strftime("%d/%m/%Y"), width=130)
        t_desc = ft.TextField(label="Descrição", expand=True)
        t_val = ft.TextField(label="Valor", width=130, keyboard_type="number", on_change=mascara_dinheiro)
        t_tipo = ft.Dropdown(width=100, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")
        
        txt_ganhou = ft.Text("Entradas: R$ 0,00", color="#4ade80")
        txt_gastou = ft.Text("Saídas: R$ 0,00", color="#f87171")
        txt_saldo = ft.Text("Saldo: R$ 0,00", size=16, weight="bold")
        
        meses = get_meses(); m_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
        if m_atual not in meses: meses.append(m_atual)
        dd_mes = ft.Dropdown(width=140, options=[ft.dropdown.Option(m) for m in meses], value=m_atual)
        
        lista_extrato = ft.Column(spacing=5) # Sem scroll aqui (usa o da página)

        def render():
            d = listar(dd_mes.value)
            ent = sum(r[5] for r in d if r[5]>0); sai = abs(sum(r[5] for r in d if r[5]<0)); bal = ent-sai
            txt_ganhou.value = f"Ent: {formatar_moeda_visual(ent)}"
            txt_gastou.value = f"Sai: {formatar_moeda_visual(sai)}"
            txt_saldo.value = f"Saldo: {formatar_moeda_visual(bal)}"
            txt_saldo.color = "#4ade80" if bal >= 0 else "#f87171"
            
            lista_extrato.controls.clear()
            for r in d:
                cor = "#f87171" if r[5]<0 else "#4ade80"
                btn = ft.IconButton(icon="delete", icon_color="grey", on_click=lambda e, x=r[0]: (deletar(x), render(), page.update()))
                lista_extrato.controls.append(ft.Container(
                    content=ft.Row([ft.Text(r[1], width=80), ft.Text(r[2], expand=True), ft.Text(f"{r[5]:.2f}", color=cor), btn]),
                    bgcolor="#1e293b", padding=10, border_radius=5
                ))
            page.update()

        def salvar(e):
            if limpar_valor(t_val.value) > 0:
                adicionar(t_data.value, t_desc.value, "Geral", t_tipo.value, limpar_valor(t_val.value))
                t_desc.value=""; t_val.value=""; notificar("Salvo!"); render()

        def pdf_acao(e):
            p = gerar_pdf(listar(dd_mes.value), dd_mes.value)
            if p: notificar(f"PDF salvo: {p}")

        dd_mes.on_change = lambda e: render()
        btn_add = ft.ElevatedButton("Salvar", bgcolor=COR_PRINCIPAL, color="white", on_click=salvar)
        render()

        # Layout Seguro (Sem Expand conflitante)
        return ft.Column([
            ft.Row([ft.Text("Extrato", size=24, weight="bold"), ft.Row([dd_mes, ft.IconButton("picture_as_pdf", on_click=pdf_acao)])], alignment="spaceBetween", wrap=True),
            ft.Container(content=ft.Column([ft.Row([txt_ganhou, txt_gastou], alignment="spaceBetween", wrap=True), ft.Divider(), txt_saldo]), bgcolor="#1e293b", padding=15, border_radius=10),
            lista_extrato,
            ft.Container(height=20),
            ft.Container(content=ft.Column([ft.Text("Novo"), ft.Row([t_data, t_tipo, t_val], wrap=True), t_desc, btn_add]), bgcolor="#1e293b", padding=15, border_radius=10),
            ft.Container(height=50) # Espaço extra fim da página
        ])

    def tela_cofrinho():
        lista_metas = ft.Column(spacing=10)
        t_nome = ft.TextField(label="Nome do Objetivo")
        t_alvo = ft.TextField(label="Valor da Meta", keyboard_type="number", on_change=mascara_dinheiro)

        def render():
            lista_metas.controls.clear()
            for m in listar_metas():
                idm, nome, alvo, atual = m[0], m[1], m[2], m[3]
                perc = int((atual/alvo)*100) if alvo>0 else 0
                t_dep = ft.TextField(label="R$", width=100, height=40, text_size=12, on_change=mascara_dinheiro)
                def dep(e, _id=idm, _t=t_dep):
                    if limpar_valor(_t.value) > 0: atualizar_meta(_id, limpar_valor(_t.value)); render(); page.update(); notificar("Guardado!")
                btn_del = ft.IconButton("delete", icon_color="red", on_click=lambda e, x=idm: (deletar_meta(x), render(), page.update()))
                lista_metas.controls.append(ft.Container(content=ft.Column([
                    ft.Row([ft.Text(nome, weight="bold"), btn_del], alignment="spaceBetween"),
                    ft.ProgressBar(value=min(perc/100, 1), color="#4ade80", bgcolor="#334155"),
                    ft.Row([ft.Text(f"Tem: {formatar_moeda_visual(atual)}"), ft.Text(f"{perc}%", color="#4ade80")], alignment="spaceBetween"),
                    ft.Row([t_dep, ft.ElevatedButton("Depositar", on_click=dep, height=35, bgcolor="#4ade80", color="black")], alignment="end")
                ]), bgcolor="#1e293b", padding=15, border_radius=10))
            page.update()

        def criar(e):
            if t_nome.value and limpar_valor(t_alvo.value) > 0: criar_meta(t_nome.value, limpar_valor(t_alvo.value)); t_nome.value=""; t_alvo.value=""; render(); notificar("Criado!")

        render()
        return ft.Column([
            ft.Text("Meus Objetivos", size=24, weight="bold"),
            lista_metas,
            ft.Container(height=20),
            ft.Container(content=ft.Column([ft.Text("Novo Objetivo"), t_nome, t_alvo, ft.ElevatedButton("Criar", on_click=criar, bgcolor=COR_PRINCIPAL, color="white")]), bgcolor="#1e293b", padding=15, border_radius=10),
            ft.Container(height=50)
        ])

    def tela_ferramentas():
        t_renda = ft.TextField(label="Renda", value=formatar_moeda_visual(get_renda()), on_change=mascara_dinheiro)
        def salv_renda(e): set_renda(limpar_valor(t_renda.value)); notificar("Salvo")
        
        t_tot = ft.TextField(label="Total", width=120, on_change=mascara_dinheiro)
        t_pag = ft.TextField(label="Pago", width=120, on_change=mascara_dinheiro)
        res_tr = ft.Text("Troco: R$ 0,00", size=16, weight="bold")
        def calc_tr(e): res_tr.value = f"Troco: {formatar_moeda_visual(limpar_valor(t_pag.value) - limpar_valor(t_tot.value))}"; page.update()

        t_dica = ft.Text("IA: Toque para dica", color=COR_PRINCIPAL); c_dica = ft.Text("")
        def get_dica(e):
            t_dica.value="Pensando..."; page.update(); d = chamar_gemini(f"Renda: {get_renda()}. Dica curta."); t_dica.value="Dica:"; c_dica.value=d if d else "Erro"; page.update()

        t_agencia = ft.TextField(label="Ex: Pagar luz 100 dia 5", expand=True)
        def agendar(e):
            d = interpretar_comando(t_agencia.value)
            if d: criar_lembrete(d.get('nome','Conta'), d.get('data',''), d.get('valor',0)); t_agencia.value=""; notificar("Agendado!")
            else: notificar("Erro IA")

        return ft.Column([
            ft.Text("Ferramentas", size=24, weight="bold"),
            ft.Container(content=ft.Row([t_renda, ft.ElevatedButton("Salvar", on_click=salv_renda)]), bgcolor="#1e293b", padding=15, border_radius=10),
            ft.Container(height=10),
            ft.Container(content=ft.Column([ft.Text("Troco"), ft.Row([t_tot, t_pag, ft.ElevatedButton("=", on_click=calc_tr)], wrap=True), res_tr]), bgcolor="#1e293b", padding=15, border_radius=10),
            ft.Container(height=10),
            ft.Container(content=ft.Column([ft.Row([t_dica, ft.IconButton("auto_awesome", on_click=get_dica)]), c_dica]), bgcolor="#1e293b", padding=15, border_radius=10),
            ft.Container(height=10),
            ft.Container(content=ft.Column([ft.Text("Agendar IA"), ft.Row([t_agencia, ft.IconButton("send", on_click=agendar)])]), bgcolor="#1e293b", padding=15, border_radius=10),
            ft.Container(height=50)
        ])

    # Navegação
    def mudar(idx):
        # Limpamos a página e redesenhamos o conteúdo
        page.clean()
        page.add(ft.SafeArea(content=ft.Container(padding=20, content=
            tela_extrato() if idx == 0 else (tela_cofrinho() if idx == 1 else tela_ferramentas())
        )))
        page.update()

    page.drawer = ft.NavigationDrawer(bgcolor="#1e293b", indicator_color=COR_PRINCIPAL, controls=[
        ft.Container(height=20), ft.Text("  FINANTEA", size=20, weight="bold", color="white"), ft.Divider(),
        ft.NavigationDrawerDestination(label="Extrato", icon="list"),
        ft.NavigationDrawerDestination(label="Objetivos", icon="savings"),
        ft.NavigationDrawerDestination(label="Ferramentas", icon="build"),
    ], on_change=lambda e: (mudar(e.control.selected_index), page.close_drawer()))

    def abrir_menu(e): page.drawer.open = True; page.update()
    page.appbar = ft.AppBar(leading=ft.IconButton("menu", on_click=abrir_menu), title=ft.Text("Finantea"), bgcolor="#0f172a")

    # Início (Substitui o loading)
    if not is_intro_ok(): 
        page.clean(); page.add(ft.SafeArea(content=tela_onboarding()))
    else: 
        mudar(0) # Carrega Extrato

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
