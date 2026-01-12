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
# 0. CONFIGURAÇÃO (NATIVO - BLINDADO)
# ==============================================================================
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")
logging.getLogger("flet").setLevel(logging.ERROR)

DB_NAME = "dados_financeiros.db"
# Cria pasta de comprovantes se permitido (evita erro de permissão no Android)
try:
    if not os.path.exists("comprovantes"): os.makedirs("comprovantes")
except: pass

def carregar_env_manual():
    """
    Lê o arquivo .env buscando na mesma pasta do script main.py.
    Isso é CRUCIAL para o Android encontrar a chave gerada pelo GitHub Actions.
    """
    try:
        # Usa o diretório onde o main.py está, que é mais seguro no Android do que getcwd()
        base_path = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(base_path, ".env")
        
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for linha in f:
                    if "=" in linha and not linha.strip().startswith("#"):
                        k, v = linha.strip().split("=", 1)
                        os.environ[k] = v.strip() # Remove espaços extras e quebras de linha
    except Exception as e:
        print(f"Nota: .env não carregado ({e})")

# Executa o carregamento imediatamente
carregar_env_manual()

# ==============================================================================
# 1. CÉREBRO DA AUTIAH (VIA HTTP - SEM INSTALAR NADA)
# ==============================================================================
API_KEY = os.getenv("API_KEY", "") 
TEM_IA = True

def chamar_autiah(prompt_usuario):
    # Se a chave não for encontrada, retorna aviso (mas o app não quebra)
    if not API_KEY or "COLE_SUA" in API_KEY: return None
    
    system_instruction = """
    Você é a Autiah, a IA do app Finantea.
    Seu tom é: Acolhedor, direto e literal.
    Responda curto (máximo 40 palavras).
    """
    
    prompt_final = f"{system_instruction}\n\nUsuário: {prompt_usuario}"
    
    modelos = ["gemini-1.5-flash", "gemini-pro"]
    for modelo in modelos:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={API_KEY}"
            headers = {'Content-Type': 'application/json'}
            data = json.dumps({"contents": [{"parts": [{"text": prompt_final}]}]}).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req) as r:
                res = json.loads(r.read().decode('utf-8'))
                if 'candidates' in res: return res['candidates'][0]['content']['parts'][0]['text']
        except: continue
    return "Autiah offline."

def interpretar_comando(texto):
    if not TEM_IA: return None
    try:
        p = f"Extraia JSON agendamento. Hoje: {datetime.now().strftime('%d/%m/%Y')}. Texto: '{texto}'. Retorne APENAS: {{'nome': str, 'valor': float, 'data': 'dd/mm/aaaa'}}"
        t = chamar_autiah(p) 
        if t:
            t = t.replace("```json", "").replace("```", "").strip()
            if "{" in t: return json.loads(t[t.find("{"):t.rfind("}")+1])
    except: return None

# ==============================================================================
# 2. SISTEMA (DB)
# ==============================================================================
def conectar_bd():
    try:
        # Garante que o DB seja criado na mesma pasta do script (seguro para Android)
        base_path = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_path, DB_NAME)
        
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS lembretes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, data_vencimento TEXT, valor REAL, status TEXT, anexo TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS perfil (id INTEGER PRIMARY KEY, tipo TEXT UNIQUE, valor REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS assinaturas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor REAL, em_uso INTEGER DEFAULT 1)")
        conn.commit()
        return conn, cursor
    except: return None, None

conn = None
cursor = None

def limpar_valor(texto):
    try:
        v = re.sub(r'[^\d.,]', '', str(texto))
        if ',' in v and '.' in v: v = v.replace('.', '').replace(',', '.')
        elif ',' in v: v = v.replace(',', '.')
        return float(v)
    except: return 0.0

def formatar_moeda_visual(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- Helpers ---
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

def criar_lembrete(n, d, v): cursor.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status) VALUES (?, ?, ?, 'Pendente')", (n, d, v)); conn.commit()
def set_renda(v): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (v,)); conn.commit()
def get_renda(): cursor.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = cursor.fetchone(); return res[0] if res else 0.0
def set_intro_ok(): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); conn.commit()
def is_intro_ok(): cursor.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = cursor.fetchone(); return True if res and res[0] == 1 else False

def adicionar_assinatura(n, v): cursor.execute("INSERT INTO assinaturas (nome, valor, em_uso) VALUES (?, ?, 1)", (n, v)); conn.commit()
def listar_assinaturas(): cursor.execute("SELECT * FROM assinaturas"); return cursor.fetchall()
def toggle_uso_assinatura(id_ass, status): cursor.execute("UPDATE assinaturas SET em_uso = ? WHERE id = ?", (0 if status==1 else 1, id_ass)); conn.commit()
def deletar_assinatura(id_ass): cursor.execute("DELETE FROM assinaturas WHERE id = ?", (id_ass,)); conn.commit()

# ==============================================================================
# 3. PDF
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
# 4. INTERFACE (COMPATÍVEL ANDROID V53)
# ==============================================================================
def main(page: ft.Page):
    try:
        page.title = "Finantea"
        page.theme_mode = "dark"
        page.bgcolor = "#0f172a"
        page.padding = 0
        page.scroll = ft.ScrollMode.AUTO 
        COR_PRINCIPAL = "#0ea5e9"

        global conn, cursor
        conn, cursor = conectar_bd()
        if not conn:
            page.add(ft.Text("Erro Crítico de BD", color="red"))
            return

        def notificar(msg, cor="green"):
            page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=cor)
            page.snack_bar.open = True
            page.update()

        def mascara_dinheiro(e):
            v = "".join(filter(str.isdigit, e.control.value))
            e.control.value = f"R$ {int(v)/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if v else ""
            e.control.update()

        def barra_simbolos():
            return ft.Container(content=ft.Row([
                ft.Icon(name=ft.icons.EXTENSION, color="#007ACC"), 
                ft.Icon(name=ft.icons.WB_SUNNY, color="#fbbf24"), 
                ft.Icon(name=ft.icons.ALL_INCLUSIVE, color="red")
            ], alignment="center", spacing=20), padding=20)

        # --- TELAS ---
        
        # 0. ONBOARDING
        def tela_onboarding():
            # USANDO 'PREFIX' PARA EVITAR ERRO NO ANDROID
            t_renda = ft.TextField(label="Renda Mensal", prefix=ft.Text("R$ "), keyboard_type="number", on_change=mascara_dinheiro, width=300)
            def ir(e):
                if limpar_valor(t_renda.value) > 0: set_renda(limpar_valor(t_renda.value)); set_intro_ok(); mudar(0)
            return ft.Container(padding=20, content=ft.Column([
                ft.Container(height=50),
                ft.Icon(name="rocket_launch", size=60, color=COR_PRINCIPAL),
                ft.Text("Bem-vindo!", size=24, weight="bold"),
                t_renda,
                ft.ElevatedButton("Iniciar", bgcolor=COR_PRINCIPAL, color="white", on_click=ir, width=200)
            ], horizontal_alignment="center"))

        # 1. EXTRATO
        def tela_extrato():
            t_data = ft.TextField(label="Data", value=datetime.now().strftime("%d/%m/%Y"), width=160)
            t_desc = ft.TextField(label="Descrição", expand=True)
            t_val = ft.TextField(label="Valor", width=130, keyboard_type="number", on_change=mascara_dinheiro)
            t_tipo = ft.Dropdown(width=100, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")
            
            txt_ganhou = ft.Text("Entradas: R$ 0,00", color="#4ade80")
            txt_gastou = ft.Text("Saídas: R$ 0,00", color="#f87171")
            txt_saldo = ft.Text("Saldo: R$ 0,00", size=16, weight="bold")
            
            meses = get_meses(); m_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
            if m_atual not in meses: meses.append(m_atual)
            dd_mes = ft.Dropdown(width=140, options=[ft.dropdown.Option(m) for m in meses], value=m_atual)
            
            lista_extrato = ft.Column(spacing=5) 

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
                if p: notificar(f"PDF gerado.")

            dd_mes.on_change = lambda e: render()
            btn_add = ft.ElevatedButton("Salvar", bgcolor=COR_PRINCIPAL, color="white", on_click=salvar)
            render()

            return ft.Column([
                ft.Row([ft.Text("Extrato", size=24, weight="bold"), ft.Row([dd_mes, ft.IconButton(icon="picture_as_pdf", on_click=pdf_acao)])], alignment="spaceBetween", wrap=True),
                ft.Container(content=ft.Column([ft.Row([txt_ganhou, txt_gastou], alignment="spaceBetween", wrap=True), ft.Divider(), txt_saldo]), bgcolor="#1e293b", padding=15, border_radius=10),
                lista_extrato,
                ft.Container(height=20),
                ft.Container(content=ft.Column([ft.Text("Novo Lançamento", weight="bold"), ft.Row([t_data, t_tipo, t_val], wrap=True), t_desc, btn_add]), bgcolor="#1e293b", padding=15, border_radius=10),
                ft.Container(height=50)
            ])

        # 2. FERRAMENTAS
        def tela_ferramentas():
            t_renda = ft.TextField(label="Renda", value=formatar_moeda_visual(get_renda()), on_change=mascara_dinheiro)
            def salv_renda(e): set_renda(limpar_valor(t_renda.value)); notificar("Salvo")
            box_perfil = ft.Container(content=ft.Row([t_renda, ft.ElevatedButton("Atualizar", on_click=salv_renda)]), bgcolor="#1e293b", padding=15, border_radius=10)

            # Preço de Vida (USANDO PREFIX PARA EVITAR ERRO)
            tr = get_renda()/160 if get_renda()>0 else 0
            t_pv = ft.TextField(label="Preço do Item", prefix=ft.Text("R$ "), on_change=mascara_dinheiro, expand=True)
            txt_pv = ft.Text("Digite valor...", italic=True)
            def calc_pv(e):
                if tr <= 0: txt_pv.value = "Defina renda!"; return
                h = limpar_valor(t_pv.value)/tr
                txt_pv.value = f"Custa: {h:.1f} horas de trabalho." if h>1 else f"Custa: {int(h*60)} minutos."
                page.update()
            box_vida = ft.Container(content=ft.Column([ft.Text("Preço de Vida", weight="bold"), ft.Row([t_pv, ft.IconButton(icon="calculate", on_click=calc_pv)]), txt_pv]), bgcolor="#1e293b", padding=15, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4,"#fbbf24")))

            # Troco
            t_tot = ft.TextField(label="Total", width=130, on_change=mascara_dinheiro); t_pag = ft.TextField(label="Pago", width=130, on_change=mascara_dinheiro); res_tr = ft.Text("Troco: R$ 0,00", weight="bold")
            def calc_tr(e): res_tr.value = f"Troco: {formatar_moeda_visual(limpar_valor(t_pag.value) - limpar_valor(t_tot.value))}"; page.update()
            box_troco = ft.Container(content=ft.Column([ft.Text("Calc. Troco", weight="bold"), ft.Row([t_tot, t_pag], wrap=True), ft.ElevatedButton("Calcular", on_click=calc_tr), res_tr]), bgcolor="#1e293b", padding=15, border_radius=10)

            # Juros
            j_val = ft.TextField(label="Valor", width=130, on_change=mascara_dinheiro); j_tax = ft.TextField(label="Juros %", width=80); j_parc = ft.TextField(label="Parc.", width=80); j_res = ft.Text("")
            def calc_jur(e):
                try:
                    v = limpar_valor(j_val.value); i = float(j_tax.value.replace(",","."))/100; n = int(j_parc.value)
                    tot = v * ((1+i)**n); j_res.value = f"Total: {formatar_moeda_visual(tot)}\nJuros: {formatar_moeda_visual(tot-v)}"; page.update()
                except: pass
            box_juros = ft.Container(content=ft.Column([ft.Text("Calc. Juros", weight="bold"), ft.Row([j_val, j_tax, j_parc], wrap=True), ft.ElevatedButton("Calcular", on_click=calc_jur), j_res]), bgcolor="#1e293b", padding=15, border_radius=10)

            # IA & Chat
            t_dica = ft.Text("IA: Toque para dica", color=COR_PRINCIPAL, weight="bold"); c_dica = ft.Text("")
            def get_dica(e):
                t_dica.value="Pensando..."; page.update(); d = chamar_autiah(f"Renda: {get_renda()}. Dica curta."); t_dica.value="Dica:"; c_dica.value=d if d else "Erro"; page.update()
            
            t_chat = ft.TextField(label="Chat Autiah...", expand=True); r_chat = ft.Text("")
            def chat(e):
                r_chat.value="..."; page.update(); r_chat.value = chamar_autiah(t_chat.value) or "Erro"; page.update()

            t_ag = ft.TextField(label="Ex: Pagar luz 100 dia 5", expand=True)
            def ag(e):
                d = interpretar_comando(t_ag.value)
                if d: criar_lembrete(d.get('nome','Conta'), d.get('data',''), d.get('valor',0)); t_ag.value=""; notificar("Agendado!")
                else: notificar("Erro", "red")

            return ft.Column([
                ft.Text("Ferramentas", size=24, weight="bold"), 
                box_perfil, ft.Container(height=10),
                box_vida, ft.Container(height=10),
                box_troco, ft.Container(height=10),
                box_juros, ft.Container(height=10),
                ft.Container(content=ft.Column([ft.Row([t_dica, ft.IconButton(icon="auto_awesome", on_click=get_dica)]), c_dica]), bgcolor="#1e293b", padding=15, border_radius=10),
                ft.Container(height=10),
                ft.Container(content=ft.Column([ft.Text("Agendar"), ft.Row([t_ag, ft.IconButton(icon="send", on_click=ag)])]), bgcolor="#1e293b", padding=15, border_radius=10),
                ft.Container(height=10),
                ft.Container(content=ft.Column([ft.Text("Chat"), ft.Row([t_chat, ft.IconButton(icon="chat", on_click=chat)]), r_chat]), bgcolor="#1e293b", padding=15, border_radius=10),
                ft.Container(height=50)
            ])

        # 3. CAÇADOR DE ASSINATURAS
        def tela_assinaturas():
            lista_ass = ft.Column(spacing=10)
            t_nome = ft.TextField(label="Nome (Netflix)", expand=True)
            t_val = ft.TextField(label="Valor", width=120, on_change=mascara_dinheiro)

            def render_ass():
                lista_ass.controls.clear()
                asss = listar_assinaturas()
                total = sum(a[2] for a in asss)
                lista_ass.controls.append(ft.Container(content=ft.Text(f"Total Mensal: {formatar_moeda_visual(total)}", weight="bold"), bgcolor="#334155", padding=10, border_radius=5))
                
                for a in asss:
                    id_a, nome, val, uso = a
                    cor = "#4ade80" if uso else "#f87171"; txt = "Em uso" if uso else "CANCELAR?"
                    def toggle(e, x=id_a, s=uso): toggle_uso_assinatura(x, s); render_ass(); page.update()
                    def delete(e, x=id_a): deletar_assinatura(x); render_ass(); page.update()
                    
                    card = ft.Container(content=ft.Row([
                        ft.Column([ft.Text(nome, weight="bold"), ft.Text(formatar_moeda_visual(val), size=12)], expand=True),
                        ft.Column([ft.Text(txt, color=cor, size=12, weight="bold"), ft.IconButton(icon=ft.icons.THUMB_UP if uso else ft.icons.THUMB_DOWN, icon_color=cor, on_click=toggle)]),
                        ft.IconButton(icon="delete", icon_color="grey", on_click=delete)
                    ]), bgcolor="#1e293b", padding=10, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, cor)))
                    lista_ass.controls.append(card)

            def add(e):
                if t_nome.value and limpar_valor(t_val.value) > 0:
                    adicionar_assinatura(t_nome.value, limpar_valor(t_val.value)); t_nome.value=""; t_val.value=""; render_ass(); page.update()

            render_ass()
            return ft.Column([
                ft.Text("Caçador de Assinaturas", size=24, weight="bold"),
                ft.Text("Check de Realidade: Você usa mesmo?", size=12, color="grey"),
                ft.Container(height=10),
                lista_ass,
                ft.Container(height=20),
                ft.Container(content=ft.Row([t_nome, t_val, ft.IconButton(icon="add_circle", icon_color=COR_PRINCIPAL, icon_size=40, on_click=add)]), bgcolor="#1e293b", padding=10, border_radius=10),
                ft.Container(height=50)
            ])

        # Navegação Segura
        def mudar(idx):
            page.clean()
            if idx == 0: page.add(ft.SafeArea(content=ft.Container(padding=20, content=tela_extrato())))
            elif idx == 1: page.add(ft.SafeArea(content=ft.Container(padding=20, content=tela_ferramentas())))
            elif idx == 2: page.add(ft.SafeArea(content=ft.Container(padding=20, content=tela_assinaturas())))
            page.update()

        def menu_change(e):
            idx = e.control.selected_index
            if idx == 3: # Botão Doar
                page.set_clipboard("85996994887"); notificar("Pix copiado! Obrigado."); page.drawer.open=False; page.update()
            else:
                mudar(idx); page.drawer.open=False; page.update()

        page.drawer = ft.NavigationDrawer(bgcolor="#1e293b", indicator_color=COR_PRINCIPAL, controls=[
            ft.Container(height=20), ft.Text("  FINANTEA", size=20, weight="bold", color="white"), ft.Divider(),
            ft.NavigationDrawerDestination(label="Extrato", icon="list"),
            ft.NavigationDrawerDestination(label="Ferramentas", icon="build"),
            ft.NavigationDrawerDestination(label="Assinaturas", icon="subscriptions"),
            ft.Divider(),
            ft.NavigationDrawerDestination(label="Doar Café", icon="coffee")
        ], on_change=menu_change)

        def abrir_menu(e): page.drawer.open = True; page.update()
        page.appbar = ft.AppBar(leading=ft.IconButton(icon="menu", on_click=abrir_menu), title=ft.Text("Finantea"), bgcolor="#0f172a")

        # Início
        if not is_intro_ok(): page.add(ft.SafeArea(content=tela_onboarding()))
        else: mudar(0)

    except Exception as e:
        page.clean(); page.add(ft.Text(f"Erro Fatal: {e}", color="red"))

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
