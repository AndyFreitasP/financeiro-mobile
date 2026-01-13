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
# 0. CONFIGURAÇÃO E DEBUGGER VISUAL
# ==============================================================================
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")
logging.getLogger("flet").setLevel(logging.ERROR)

# Variáveis Globais
CONN = None
CURSOR = None
API_KEY = ""
TEM_IA = False
LOG_ERROS = [] # Lista para guardar erros e mostrar na tela

def log_sistema(msg):
    print(msg)
    LOG_ERROS.append(str(msg))

# ==============================================================================
# 1. SISTEMA (BANCO DE DADOS E LÓGICA)
# ==============================================================================
def inicializar_sistema():
    global CONN, CURSOR, API_KEY, TEM_IA
    
    # 1. Carregar Chave
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(base_path, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    if "API_KEY" in line and "=" in line:
                        API_KEY = line.split("=", 1)[1].strip()
                        TEM_IA = True
            log_sistema("Chave API encontrada.")
        else:
            log_sistema("Arquivo .env não encontrado.")
    except Exception as e:
        log_sistema(f"Erro .env: {e}")

    # 2. Conectar BD (Caminho Simples = Mais Seguro no Android com Flet)
    try:
        db_file = os.path.join(os.getcwd(), "finantea.db")
        CONN = sqlite3.connect(db_file, check_same_thread=False)
        CURSOR = CONN.cursor()
        
        sqls = [
            "CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)",
            "CREATE TABLE IF NOT EXISTS lembretes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, data_vencimento TEXT, valor REAL, status TEXT, anexo TEXT)",
            "CREATE TABLE IF NOT EXISTS perfil (id INTEGER PRIMARY KEY, tipo TEXT UNIQUE, valor REAL)",
            "CREATE TABLE IF NOT EXISTS assinaturas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, em_uso INTEGER DEFAULT 1)"
        ]
        for s in sqls: CURSOR.execute(s)
        CONN.commit()
        log_sistema(f"Banco conectado: {db_file}")
    except Exception as e:
        log_sistema(f"ERRO CRÍTICO BD: {e}")

# Helpers
def formatar_moeda(v):
    if v is None: v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(texto):
    try:
        v = re.sub(r'[^\d.,]', '', str(texto))
        if ',' in v and '.' in v: v = v.replace('.', '').replace(',', '.')
        elif ',' in v: v = v.replace(',', '.')
        return float(v)
    except: return 0.0

# CRUD
def db_add(data, desc, tipo, valor):
    try:
        v = abs(valor) * -1 if tipo == "Despesa" else abs(valor)
        CURSOR.execute("INSERT INTO financeiro (data, descricao, categoria, tipo, valor) VALUES (?, ?, 'Geral', ?, ?)", (data, desc, tipo, v))
        CONN.commit()
    except Exception as e: log_sistema(f"Erro add: {e}")

def db_list(mes):
    try:
        CURSOR.execute("SELECT * FROM financeiro WHERE data LIKE ? ORDER BY id DESC", [f"%/{mes}"])
        return CURSOR.fetchall()
    except: return []

def db_del(id_i): CURSOR.execute("DELETE FROM financeiro WHERE id = ?", (id_i,)); CONN.commit()

def db_meses():
    try:
        m = set(); CURSOR.execute("SELECT data FROM financeiro")
        for r in CURSOR:
            try: m.add((datetime.strptime(r[0], "%d/%m/%Y").year, datetime.strptime(r[0], "%d/%m/%Y").month))
            except: continue
        now = datetime.now(); m.add((now.year, now.month))
        return [f"{mm:02d}/{y}" for y, mm in sorted(list(m))]
    except: return [datetime.now().strftime("%m/%Y")]

def db_perfil_set(v): CURSOR.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (v,)); CONN.commit()
def db_perfil_get(): 
    try: 
        CURSOR.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = CURSOR.fetchone()
        return res[0] if res else 0.0
    except: return 0.0

def db_intro_check(): 
    try:
        CURSOR.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = CURSOR.fetchone()
        return True if res and res[0] == 1 else False
    except: return False

def db_intro_set(): CURSOR.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); CONN.commit()

def db_ass_add(n, v): CURSOR.execute("INSERT INTO assinaturas (nome, valor, em_uso) VALUES (?, ?, 1)", (n, v)); CONN.commit()
def db_ass_list(): CURSOR.execute("SELECT * FROM assinaturas"); return CURSOR.fetchall()
def db_ass_toggle(id_a, s): CURSOR.execute("UPDATE assinaturas SET em_uso = ? WHERE id = ?", (0 if s else 1, id_a)); CONN.commit()
def db_ass_del(id_a): CURSOR.execute("DELETE FROM assinaturas WHERE id = ?", (id_a,)); CONN.commit()
def db_lembrete_add(n, d, v): CURSOR.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status) VALUES (?, ?, ?, 'Pendente')", (n, d, v)); CONN.commit()

# IA
def chamar_autiah(prompt):
    if not TEM_IA: return "Erro: Chave API não configurada."
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        data = json.dumps({"contents": [{"parts": [{"text": "Você é a Autiah. " + prompt}]}]}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode('utf-8'))
            if 'candidates' in res: return res['candidates'][0]['content']['parts'][0]['text']
    except Exception as e: return f"Erro IA: {e}"
    return "IA sem resposta."

def interpretar_agendamento(texto):
    if not TEM_IA: return None
    try:
        res = chamar_autiah(f"Extraia JSON: {{'nome': str, 'valor': float, 'data': 'dd/mm/aaaa'}}. Hoje {datetime.now().strftime('%d/%m/%Y')}. Texto: {texto}")
        if res:
            res = res.replace("```json", "").replace("```", "").strip()
            return json.loads(res[res.find("{"):res.rfind("}")+1])
    except: return None

# PDF
class PDFRelatorio(FPDF):
    def header(self):
        self.set_fill_color(14,165,233); self.rect(0,0,210,30,'F'); self.set_y(8)
        self.set_font('Arial','B',18); self.set_text_color(255); self.cell(0,10,"FINANTEA",0,1,'C'); self.ln(15)
def gerar_pdf(dados, mes):
    try:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f"extrato.pdf")
        pdf = PDFRelatorio(); pdf.add_page(); pdf.set_text_color(0); pdf.set_font("Arial","B",12)
        pdf.cell(0,10,f"Ref: {mes}",ln=True); pdf.ln(2); pdf.set_fill_color(240); pdf.set_font("Arial","",10)
        for r in dados:
            pdf.ln(); pdf.cell(30,8,r[1],1,0,'C'); pdf.cell(110,8,f" {r[2][:40]}",1,0,'L'); pdf.cell(40,8,f"{r[5]:,.2f}",1,1,'R')
        pdf.output(path); return path
    except Exception as e: log_sistema(f"Erro PDF: {e}"); return None

# ==============================================================================
# 2. INTERFACE (V61 - LAYOUT NATIVO)
# ==============================================================================
def main(page: ft.Page):
    # CONFIGURAÇÃO DE SEGURANÇA VISUAL
    page.title = "Finantea"
    page.theme_mode = "dark"
    page.bgcolor = "#0f172a"
    page.padding = 0
    
    # IMPORTANTE: Desativar scroll da página. As ListViews internas farão o scroll.
    # Isso impede a tela azul/vazia.
    page.scroll = None 
    
    COR_PRINCIPAL = "#0ea5e9"
    
    # Widget de Debug (Aparece no topo se houver erros)
    txt_debug = ft.Text("", color="yellow", size=12, selectable=True)
    
    def atualizar_debug():
        if LOG_ERROS:
            txt_debug.value = "LOGS:\n" + "\n".join(LOG_ERROS[-3:]) # Mostra os ultimos 3
            page.update()

    inicializar_sistema()
    atualizar_debug()

    def notificar(m, c="green"):
        page.snack_bar = ft.SnackBar(ft.Text(m), bgcolor=c); page.snack_bar.open=True; page.update()

    def mascara_dinheiro(e):
        v = "".join(filter(str.isdigit, e.control.value))
        e.control.value = f"R$ {int(v)/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if v else ""
        e.control.update()

    # --- TELAS (Usando Column com expand=True para preencher a tela) ---
    
    def tela_onboarding():
        t_renda = ft.TextField(label="Renda Mensal", prefix=ft.Text("R$ "), keyboard_type="number", on_change=mascara_dinheiro, width=300)
        def ir(e):
            if limpar_valor(t_renda.value) > 0: db_perfil_set(limpar_valor(t_renda.value)); db_intro_set(); navegar_para(0)
        
        return ft.Column([
            ft.Container(height=50),
            ft.Icon("rocket_launch", size=60, color=COR_PRINCIPAL),
            ft.Text("Bem-vindo ao Finantea!", size=24, weight="bold"),
            txt_debug, # Mostra erro aqui se houver
            t_renda,
            ft.ElevatedButton("Iniciar", bgcolor=COR_PRINCIPAL, color="white", on_click=ir, width=200)
        ], horizontal_alignment="center", alignment="center", expand=True)

    def tela_extrato():
        # Cabeçalho
        meses = db_meses(); m_atual = meses[-1] if meses else datetime.now().strftime("%m/%Y")
        dd_mes = ft.Dropdown(width=130, options=[ft.dropdown.Option(m) for m in meses], value=m_atual)
        btn_pdf = ft.IconButton("picture_as_pdf", icon_color=COR_PRINCIPAL, on_click=lambda e: notificar(f"PDF: {gerar_pdf(db_list(dd_mes.value), dd_mes.value)}"))
        
        # Resumo
        txt_resumo = ft.Text("Carregando...", weight="bold")
        
        # Lista (ListView com expand=True para ocupar o meio da tela e rolar)
        lv_lista = ft.ListView(expand=True, spacing=10, padding=10)

        # Inputs Rodapé
        t_data = ft.TextField(label="Data", value=datetime.now().strftime("%d/%m/%Y"), width=100)
        t_desc = ft.TextField(label="Desc", expand=True)
        t_val = ft.TextField(label="Val", width=100, keyboard_type="number", on_change=mascara_dinheiro)
        t_tipo = ft.Dropdown(width=80, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")

        def render():
            try:
                d = db_list(dd_mes.value)
                e = sum(r[5] for r in d if r[5]>0); s = abs(sum(r[5] for r in d if r[5]<0))
                txt_resumo.value = f"Saldo: {formatar_moeda(e-s)} (Ent: {formatar_moeda(e)} | Sai: {formatar_moeda(s)})"
                
                lv_lista.controls.clear()
                for r in d:
                    cor = "#f87171" if r[5]<0 else "#4ade80"
                    lv_lista.controls.append(ft.Container(bgcolor="#1e293b", padding=10, border_radius=5, content=ft.Row([
                        ft.Text(r[1], width=70, size=12), ft.Text(r[2], expand=True), ft.Text(f"{r[5]:.2f}", color=cor),
                        ft.IconButton("delete", icon_color="grey", on_click=lambda e, x=r[0]: (db_del(x), render(), page.update()))
                    ])))
                page.update()
            except Exception as e: log_sistema(f"Erro Render: {e}"); atualizar_debug()

        def add(e):
            if limpar_valor(t_val.value) > 0:
                db_add(t_data.value, t_desc.value, t_tipo.value, limpar_valor(t_val.value))
                t_desc.value=""; t_val.value=""; notificar("Salvo"); render()

        dd_mes.on_change = lambda e: render()
        render()

        return ft.Column([
            ft.Container(padding=10, content=ft.Row([ft.Text("Extrato", size=24, weight="bold"), ft.Row([dd_mes, btn_pdf])], alignment="spaceBetween")),
            ft.Container(padding=10, bgcolor="#1e293b", content=txt_resumo),
            txt_debug, # Debug visível
            lv_lista, # Este elemento vai expandir e rolar
            ft.Container(padding=10, bgcolor="#1e293b", content=ft.Column([
                ft.Text("Novo:"),
                ft.Row([t_data, t_desc]),
                ft.Row([t_tipo, t_val, ft.IconButton("send", icon_color=COR_PRINCIPAL, on_click=add)])
            ]))
        ], expand=True) # Coluna Principal expande na tela

    def tela_ferramentas():
        # ListView Principal
        lv = ft.ListView(expand=True, spacing=15, padding=15)
        
        # Renda
        t_renda = ft.TextField(label="Renda", value=formatar_moeda(db_perfil_get()), on_change=mascara_dinheiro)
        lv.controls.append(ft.Container(padding=10, bgcolor="#1e293b", border_radius=10, content=ft.Row([t_renda, ft.IconButton("save", on_click=lambda e: (db_perfil_set(limpar_valor(t_renda.value)), notificar("Salvo")))])))

        # Preço Vida
        t_pv = ft.TextField(label="Preço Item", prefix=ft.Text("R$ "), on_change=mascara_dinheiro, expand=True); r_pv = ft.Text("Custo em vida...", italic=True)
        def c_pv(e):
            r = db_perfil_get(); h = limpar_valor(t_pv.value)/(r/160) if r>0 else 0
            r_pv.value = f"{h:.1f} horas" if h>1 else f"{int(h*60)} min"; page.update()
        lv.controls.append(ft.Container(padding=10, bgcolor="#1e293b", border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, "#fbbf24")), content=ft.Column([ft.Text("Preço de Vida", weight="bold"), ft.Row([t_pv, ft.IconButton("calculate", on_click=c_pv)]), r_pv])))

        # Troco
        t_tot = ft.TextField(label="Total", width=100, on_change=mascara_dinheiro); t_pg = ft.TextField(label="Pago", width=100, on_change=mascara_dinheiro); r_tr = ft.Text("Troco: R$ 0")
        def c_tr(e): r_tr.value=f"Troco: {formatar_moeda(limpar_valor(t_pg.value)-limpar_valor(t_tot.value))}"; page.update()
        lv.controls.append(ft.Container(padding=10, bgcolor="#1e293b", border_radius=10, content=ft.Column([ft.Text("Troco", weight="bold"), ft.Row([t_tot, t_pg, ft.IconButton("calculate", on_click=c_tr)]), r_tr])))

        # Juros
        j_v = ft.TextField(label="Val", width=100, on_change=mascara_dinheiro); j_t = ft.TextField(label="%", width=60); j_p = ft.TextField(label="x", width=60); j_r = ft.Text("")
        def c_jr(e):
            try: v=limpar_valor(j_v.value); i=float(j_t.value.replace(",","."))/100; n=int(j_p.value); t=v*((1+i)**n); j_r.value=f"Tot: {formatar_moeda(t)}"; page.update()
            except: pass
        lv.controls.append(ft.Container(padding=10, bgcolor="#1e293b", border_radius=10, content=ft.Column([ft.Text("Juros", weight="bold"), ft.Row([j_v, j_t, j_p, ft.IconButton("calculate", on_click=c_jr)]), j_r])))

        # IA
        t_ch = ft.TextField(label="Autiah Chat", expand=True); r_ch = ft.Text("")
        def chat(e): r_ch.value="..."; page.update(); r=chamar_autiah(t_ch.value); r_ch.value=r; page.update()
        lv.controls.append(ft.Container(padding=10, bgcolor="#1e293b", border_radius=10, content=ft.Column([ft.Text("Chat", weight="bold"), ft.Row([t_ch, ft.IconButton("chat", on_click=chat)]), r_ch])))

        # Agendar
        t_ag = ft.TextField(label="Ex: Luz 100 dia 5", expand=True)
        def ag(e):
            d = interpretar_agendamento(t_ag.value)
            if d: db_lembrete_add(d.get('nome','Conta'), d.get('data',''), d.get('valor',0)); notificar("Agendado")
            else: notificar("Erro IA", "red")
        lv.controls.append(ft.Container(padding=10, bgcolor="#1e293b", border_radius=10, content=ft.Column([ft.Text("Agendar", weight="bold"), ft.Row([t_ag, ft.IconButton("event", on_click=ag)])])))

        return ft.Column([ft.Container(padding=15, content=ft.Text("Ferramentas", size=24, weight="bold")), txt_debug, lv], expand=True)

    def tela_assinaturas():
        t_nome = ft.TextField(label="Nome", expand=True); t_val = ft.TextField(label="Valor", width=120, on_change=mascara_dinheiro)
        lv_ass = ft.ListView(expand=True, spacing=10, padding=10)
        def render():
            lv_ass.controls.clear()
            items = db_ass_list(); total = sum(i[2] for i in items if i[3])
            lv_ass.controls.append(ft.Container(padding=10, bgcolor="#334155", border_radius=5, content=ft.Text(f"Total: {formatar_moeda(total)}", weight="bold")))
            for i in items:
                cor = "#4ade80" if i[3] else "red"; ico = "thumb_up" if i[3] else "thumb_down"
                lv_ass.controls.append(ft.Container(bgcolor="#1e293b", padding=10, border_radius=5, content=ft.Row([
                    ft.Text(i[1], weight="bold", expand=True), ft.Text(formatar_moeda(i[2])),
                    ft.IconButton(ico, icon_color=cor, on_click=lambda e, x=i[0], s=i[3]: (db_ass_toggle(x, s), render(), page.update())),
                    ft.IconButton("delete", icon_color="grey", on_click=lambda e, x=i[0]: (db_ass_del(x), render(), page.update()))])))
            page.update()
        def add(e):
            if limpar_valor(t_val.value) > 0: db_ass_add(t_nome.value, limpar_valor(t_val.value)); t_nome.value=""; render()
        render()
        return ft.Column([ft.Container(padding=15, content=ft.Text("Assinaturas", size=24, weight="bold")), txt_debug, lv_ass, ft.Container(padding=10, bgcolor="#1e293b", content=ft.Row([t_nome, t_val, ft.IconButton("add_circle", icon_color=COR_PRINCIPAL, on_click=add)]))], expand=True)

    # --- NAVEGAÇÃO ---
    def navegar_para(idx):
        page.clean()
        if idx == 0: page.add(ft.SafeArea(content=tela_extrato(), expand=True))
        elif idx == 1: page.add(ft.SafeArea(content=tela_ferramentas(), expand=True))
        elif idx == 2: page.add(ft.SafeArea(content=tela_assinaturas(), expand=True))
        page.update()

    def menu_evt(e):
        idx = e.control.selected_index
        if idx == 3: page.set_clipboard("85996994887"); notificar("Pix Copiado!")
        else: navegar_para(idx)
        page.drawer.open = False; page.update()

    page.drawer = ft.NavigationDrawer(bgcolor="#1e293b", indicator_color=COR_PRINCIPAL, controls=[
        ft.Container(height=20), ft.Text("  FINANTEA", size=20, weight="bold"), ft.Divider(),
        ft.NavigationDrawerDestination(label="Extrato", icon="list"),
        ft.NavigationDrawerDestination(label="Ferramentas", icon="build"),
        ft.NavigationDrawerDestination(label="Assinaturas", icon="subscriptions"),
        ft.Divider(),
        ft.NavigationDrawerDestination(label="Doar Café", icon="coffee")
    ], on_change=menu_evt)

    def abrir_menu(e): page.drawer.open=True; page.update()
    page.appbar = ft.AppBar(leading=ft.IconButton("menu", on_click=abrir_menu), title=ft.Text("Finantea"), bgcolor="#0f172a")

    if db_intro_check(): navegar_para(0)
    else: page.add(ft.SafeArea(content=tela_onboarding(), expand=True)); page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
