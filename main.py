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
from dotenv import load_dotenv

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
load_dotenv()
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")
logging.getLogger("flet").setLevel(logging.ERROR)

DB_NAME = "dados_financeiros.db"
if not os.path.exists("comprovantes"): os.makedirs("comprovantes")

# ==============================================================================
# 1. IA LITE BLINDADA (SISTEMA DE TENTATIVA MÚLTIPLA)
# ==============================================================================
# Tenta pegar do .env, senão usa o fallback (mas prefira o .env!)
API_KEY = os.getenv("API_KEY", "COLE_SUA_NOVA_CHAVE_AQUI")
TEM_IA = True

def chamar_gemini(prompt):
    if "COLE_SUA" in API_KEY or not API_KEY:
        print("AVISO: Chave API ausente.")
        return None
    
    # LISTA DE MODELOS PARA TENTAR (Se um falhar, tenta o próximo)
    modelos_para_testar = [
        "gemini-1.5-flash",       # Mais rápido e novo
        "gemini-1.5-flash-001",   # Versão estável do flash
        "gemini-pro"              # Clássico (funciona quase sempre)
    ]

    for modelo in modelos_para_testar:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req) as response:
                res_json = json.loads(response.read().decode('utf-8'))
                # Se chegou aqui, funcionou! Retorna a resposta.
                if 'candidates' in res_json and res_json['candidates']:
                    return res_json['candidates'][0]['content']['parts'][0]['text']
        except urllib.error.HTTPError as e:
            # Se for 404 (Modelo não encontrado), ignora e o loop tenta o próximo
            if e.code == 404:
                continue 
            print(f"Erro HTTP ({modelo}): {e}")
        except Exception as e:
            print(f"Erro Geral ({modelo}): {e}")
            
    return "A IA não conseguiu responder no momento."

# ==============================================================================
# 2. SISTEMA (DB + HELPERS)
# ==============================================================================
def conectar_bd():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS metas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_alvo REAL, valor_atual REAL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS lembretes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, data_vencimento TEXT, valor REAL, status TEXT DEFAULT 'Pendente', anexo TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS perfil (id INTEGER PRIMARY KEY, tipo TEXT UNIQUE, valor REAL)")
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

# CRUD
def adicionar(data, desc, cat, tipo, valor):
    v = abs(valor) * -1 if tipo == "Despesa" else abs(valor)
    cursor.execute("INSERT INTO financeiro (data, descricao, categoria, tipo, valor) VALUES (?, ?, ?, ?, ?)", (data, desc, cat, tipo, v)); conn.commit()
def listar(mes_filtro=None):
    sql = "SELECT * FROM financeiro"; p = []
    if mes_filtro: sql += " WHERE data LIKE ?"; p.append(f"%/{mes_filtro}")
    sql += " ORDER BY id DESC"; cursor.execute(sql, p); return cursor.fetchall()
def deletar(idr): cursor.execute("DELETE FROM financeiro WHERE id = ?", (idr,)); conn.commit()
def get_meses():
    m = set(); cursor.execute("SELECT data FROM financeiro")
    for r in cursor:
        try: m.add((datetime.strptime(r[0], "%d/%m/%Y").year, datetime.strptime(r[0], "%d/%m/%Y").month))
        except: continue
    now = datetime.now(); m.add((now.year, now.month)); return [f"{mm:02d}/{y}" for y, mm in sorted(list(m))]

# Metas & Lembretes
def criar_meta(n, a): cursor.execute("INSERT INTO metas (nome, valor_alvo, valor_atual) VALUES (?, ?, 0)", (n, a)); conn.commit()
def atualizar_meta(idm, v): cursor.execute("UPDATE metas SET valor_atual = valor_atual + ? WHERE id = ?", (v, idm)); conn.commit()
def listar_metas(): cursor.execute("SELECT * FROM metas"); return cursor.fetchall()
def deletar_meta(idm): cursor.execute("DELETE FROM metas WHERE id = ?", (idm,)); conn.commit()
def criar_lembrete(n, d, v): cursor.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status) VALUES (?, ?, ?, 'Pendente')", (n, d, v)); conn.commit()
def set_renda(valor): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (valor,)); conn.commit()
def get_renda(): cursor.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = cursor.fetchone(); return res[0] if res else 0.0
def set_intro_ok(): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); conn.commit()
def is_intro_ok(): cursor.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = cursor.fetchone(); return True if res and res[0] == 1 else False

def interpretar_comando(texto):
    if not TEM_IA: return None
    try:
        # Prompt mais robusto para a versão Lite
        prompt = f"""Atue como um extrator de dados. Hoje é {datetime.now().strftime('%d/%m/%Y')}. 
        Analise a frase: "{texto}".
        Se for um agendamento financeiro, retorne APENAS um JSON neste formato: {{"nome": "descricao", "valor": 0.00, "data": "dd/mm/aaaa"}}.
        Se não tiver data, use a data de hoje. Se não tiver valor, use 0.00.
        NÃO escreva nada além do JSON."""
        
        txt = chamar_gemini(prompt)
        if not txt: return None
        
        # Limpeza extra para garantir que o JSON é válido
        txt = txt.replace("```json", "").replace("```", "").strip()
        if "{" not in txt: return None # Se a IA falou algo que não é JSON
        
        return json.loads(txt)
    except: return None

# ==============================================================================
# 3. INTERFACE (V39 - ESTÁVEL)
# ==============================================================================
class RelatorioPDF(FPDF):
    def header(self):
        self.set_fill_color(255, 255, 255); self.rect(0, 0, 210, 297, 'F')
        self.set_fill_color(14, 165, 233); self.rect(0, 0, 210, 30, 'F'); self.set_y(8)
        self.set_font('Arial', 'B', 18); self.set_text_color(255, 255, 255)
        self.cell(0, 10, "FINANTEA - Extrato", 0, 1, 'C'); self.ln(15)
    def footer(self):
        self.set_y(-20); self.set_font('Arial', 'I', 8); self.set_text_color(100)
        self.cell(0, 10, 'Acessibilidade - Neurodiversidade - Inclusao', 0, 1, 'C')
        l = 210/3; y=285
        self.set_fill_color(255, 215, 0); self.rect(0, y, l, 2, 'F')
        self.set_fill_color(255, 0, 0); self.rect(l, y, l, 2, 'F')
        self.set_fill_color(0, 0, 255); self.rect(l*2, y, l, 2, 'F')

def gerar_pdf(dados, mes):
    try:
        nome = f"extrato_{mes.replace('/','_')}.pdf"
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
        pdf.output(nome); return nome
    except: return None

def main(page: ft.Page):
    page.title = "Finantea V39"
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

    def obter_dica_ia():
        if not TEM_IA: return ("IA Offline", "Sem conexão."), "grey"
        renda = get_renda()
        cursor.execute("SELECT SUM(valor) FROM financeiro"); saldo = cursor.fetchone()[0] or 0
        txt = chamar_gemini(f"Renda: R$ {renda:.2f}. Saldo: R$ {saldo:.2f}. Dica financeira curta e literal.")
        return ("Dica Clara:", txt) if txt else ("Erro", "Tente novamente."), COR_PRINCIPAL

    def barra_simbolos():
        return ft.Container(content=ft.Row([
            ft.Tooltip(message="Autismo", content=ft.Icon(ft.icons.EXTENSION, color="#007ACC")),
            ft.Tooltip(message="Deficiências Ocultas", content=ft.Icon(ft.icons.WB_SUNNY, color="#fbbf24")),
            ft.Tooltip(message="Neurodiversidade", content=ft.Icon(ft.icons.ALL_INCLUSIVE, color="red")),
        ], alignment="center", spacing=20), padding=20)

    # --- NAVEGAÇÃO CENTRAL ---
    conteudo = ft.Container(expand=True)

    def mudar(idx):
        if idx == 0: conteudo.content = tela_extrato()
        elif idx == 1: conteudo.content = tela_cofrinho()
        elif idx == 2: conteudo.content = tela_ferramentas()
        page.drawer.selected_index = idx 
        page.update()

    # --- TELA 0: ONBOARDING ---
    def tela_onboarding():
        t_renda = ft.TextField(label="Qual sua Renda Mensal?", prefix_text="R$ ", keyboard_type="number", on_change=mascara_dinheiro, text_size=20, width=300)
        
        def acao_comecar(e):
            val = limpar_valor(t_renda.value)
            if val <= 0: notificar("Digite um valor válido.", "red"); return
            set_renda(val); set_intro_ok(); notificar("Perfil Criado!"); mudar(0)
        
        def acao_pular(e):
            set_intro_ok(); notificar("Configuração pulada."); mudar(0)

        return ft.Container(alignment=ft.alignment.center, content=ft.Column([
            ft.Icon("rocket_launch", size=60, color=COR_PRINCIPAL),
            ft.Text("Bem-vindo ao Finantea!", size=24, weight="bold"),
            ft.Text("Para começar, digite quanto você recebe por mês:", color="grey"),
            t_renda,
            ft.ElevatedButton("Iniciar", bgcolor=COR_PRINCIPAL, color="white", width=200, height=50, on_click=acao_comecar),
            ft.TextButton("Pular por enquanto", on_click=acao_pular),
            ft.Container(height=30), barra_simbolos()
        ], alignment="center", horizontal_alignment="center"))

    # --- TELAS PRINCIPAIS ---
    def tela_extrato():
        lista = ft.Column(scroll="auto", expand=True)
        t_data = ft.TextField(label="Quando?", value=datetime.now().strftime("%d/%m/%Y"), width=100)
        t_desc = ft.TextField(label="Com o que?", expand=True)
        t_val = ft.TextField(label="Quanto?", width=150, keyboard_type="number", on_change=mascara_dinheiro)
        t_tipo = ft.Dropdown(width=100, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")
        
        # Placar
        txt_ganhou = ft.Text("Entradas: R$ 0,00", color="#4ade80", weight="bold")
        txt_gastou = ft.Text("Saídas: R$ 0,00", color="#f87171", weight="bold")
        txt_saldo = ft.Text("Resultado: R$ 0,00", size=16, weight="bold", color="white")
        
        meses = get_meses(); mes_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
        if mes_atual not in meses: meses.append(mes_atual)
        dd_mes = ft.Dropdown(options=[ft.dropdown.Option(m) for m in meses], value=mes_atual)

        def render():
            dados = listar(dd_mes.value)
            ent = sum(r[5] for r in dados if r[5]>0); sai = abs(sum(r[5] for r in dados if r[5]<0)); bal = ent-sai
            txt_ganhou.value = f"Entradas: {formatar_moeda_visual(ent)}"
            txt_gastou.value = f"Saídas: {formatar_moeda_visual(sai)}"
            txt_saldo.value = f"Saldo Positivo: {formatar_moeda_visual(bal)}" if bal >= 0 else f"Saldo Negativo: {formatar_moeda_visual(abs(bal))}"
            txt_saldo.color = "#4ade80" if bal >= 0 else "#f87171"
            
            lista.controls.clear()
            for r in dados:
                cor = "#f87171" if r[5]<0 else "#4ade80"
                btn = ft.IconButton(icon="delete", icon_color="grey", on_click=lambda e, x=r[0]: (deletar(x), render(), page.update()))
                lista.controls.append(ft.Container(content=ft.Row([ft.Text(r[1], width=80), ft.Text(r[2], expand=True), ft.Text(f"R$ {r[5]:.2f}", color=cor), btn]), bgcolor="#1e293b", padding=10, border_radius=5, border=ft.border.only(left=ft.border.BorderSide(4, cor))))
            page.update()

        def salvar(e):
            val = limpar_valor(t_val.value)
            if val == 0: notificar("Valor inválido.", "red"); return
            adicionar(t_data.value, t_desc.value, "Geral", t_tipo.value, val)
            t_desc.value=""; t_val.value=""; notificar("Salvo!"); render()

        def criar_pdf(e):
            d = listar(dd_mes.value)
            if not d: notificar("Sem dados.", "red"); return
            arq = gerar_pdf(d, dd_mes.value)
            if arq: notificar("PDF Gerado!"); os.startfile(arq)

        dd_mes.on_change = lambda e: render()
        btn_add = ft.ElevatedButton("Salvar", bgcolor=COR_PRINCIPAL, color="white", on_click=salvar)
        btn_pdf = ft.IconButton(icon="picture_as_pdf", icon_color=COR_PRINCIPAL, on_click=criar_pdf)

        render()
        
        # FIX DE LAYOUT V38: Container externo com padding generoso no topo
        return ft.Container(padding=ft.padding.only(left=20, right=20, top=20, bottom=20), content=ft.Column([
            ft.Row([ft.Text("Extrato Mensal", size=24, weight="bold"), ft.Row([dd_mes, btn_pdf], spacing=10)], alignment="spaceBetween"),
            ft.Container(content=ft.Column([ft.Row([txt_ganhou, txt_gastou], alignment="spaceBetween"), ft.Divider(color="grey"), ft.Row([txt_saldo], alignment="center")]), bgcolor="#1e293b", padding=15, border_radius=10, border=ft.border.all(1, "#334155")),
            ft.Container(height=10), lista,
            ft.Container(content=ft.Column([ft.Text("Novo Lançamento", weight="bold"), ft.Row([t_data, t_tipo, t_val]), ft.Row([t_desc]), btn_add]), bgcolor="#1e293b", padding=15, border_radius=10)
        ], expand=True))

    def tela_cofrinho():
        lista = ft.Column(scroll="auto", expand=True)
        t_nome = ft.TextField(label="Nome do Objetivo")
        t_alvo = ft.TextField(label="Valor da Meta", keyboard_type="number", on_change=mascara_dinheiro)

        def render():
            lista.controls.clear()
            for m in listar_metas():
                idm, nome, alvo, atual = m[0], m[1], m[2], m[3]
                perc = int((atual/alvo)*100) if alvo>0 else 0
                t_dep = ft.TextField(label="R$", width=100, height=40, text_size=12, on_change=mascara_dinheiro)
                def dep(e, _id=idm, _t=t_dep):
                    v = limpar_valor(_t.value)
                    if v > 0: atualizar_meta(_id, v); render(); page.update(); notificar(f"Adicionado {formatar_moeda_visual(v)}")
                btn_del = ft.IconButton(icon="delete", icon_color="red", on_click=lambda e, x=idm: (deletar_meta(x), render(), page.update()))
                lista.controls.append(ft.Container(content=ft.Column([
                    ft.Row([ft.Text(nome, weight="bold", size=16), btn_del], alignment="spaceBetween"),
                    ft.ProgressBar(value=min(perc/100, 1), color="#4ade80", bgcolor="#334155"),
                    ft.Row([ft.Text(f"Tem: {formatar_moeda_visual(atual)}"), ft.Text(f"{perc}%", color="#4ade80")], alignment="spaceBetween"),
                    ft.Row([t_dep, ft.ElevatedButton("Guardar", on_click=dep, height=35, bgcolor="#4ade80", color="black")], alignment="end")
                ]), bgcolor="#1e293b", padding=15, border_radius=10))
            page.update()

        def criar(e):
            val = limpar_valor(t_alvo.value)
            if t_nome.value and val > 0: criar_meta(t_nome.value, val); t_nome.value=""; t_alvo.value=""; render(); notificar("Objetivo Criado!")

        render()
        return ft.Container(padding=ft.padding.only(left=20, right=20, top=20, bottom=20), content=ft.Column([ft.Text("Meus Objetivos", size=24, weight="bold"), lista, ft.Container(content=ft.Column([ft.Text("Novo Objetivo", weight="bold"), t_nome, t_alvo, ft.ElevatedButton("Criar", on_click=criar, bgcolor=COR_PRINCIPAL, color="white")]), bgcolor="#1e293b", padding=15, border_radius=10)], expand=True))

    def tela_ferramentas():
        t_renda = ft.TextField(label="Renda Mensal", value=formatar_moeda_visual(get_renda()), width=150, on_change=mascara_dinheiro)
        def salvar_renda(e): set_renda(limpar_valor(t_renda.value)); notificar("Renda atualizada.")
        box_perfil = ft.Container(content=ft.Row([t_renda, ft.ElevatedButton("Atualizar", on_click=salvar_renda)]), bgcolor="#1e293b", padding=15, border_radius=10)

        t_tot = ft.TextField(label="Total Compra", width=120, on_change=mascara_dinheiro)
        t_pag = ft.TextField(label="Valor Pago", width=120, on_change=mascara_dinheiro)
        res = ft.Text("Troco: R$ 0,00", size=16, weight="bold")
        def calc_troco(e): tr = limpar_valor(t_pag.value) - limpar_valor(t_tot.value); res.value = f"Troco: {formatar_moeda_visual(tr)}"; res.color = "green" if tr >= 0 else "red"; page.update()
        box_troco = ft.Container(content=ft.Column([ft.Text("Calculadora de Troco"), ft.Row([t_tot, t_pag, ft.ElevatedButton("=", on_click=calc_troco)]), res]), bgcolor="#1e293b", padding=15, border_radius=10)

        j_val = ft.TextField(label="Valor Compra", width=120, on_change=mascara_dinheiro); j_taxa = ft.TextField(label="Juros (%)", width=120); j_parc = ft.TextField(label="Parcelas", width=80)
        j_res = ft.Text("Vale a pena parcelar?", color="grey")
        def calc_juros(e):
            try:
                v = limpar_valor(j_val.value); i = float(j_taxa.value.replace(",", "."))/100; n = int(j_parc.value)
                tot = v * ((1+i)**n); jur = tot - v
                j_res.value = f"Total Final: {formatar_moeda_visual(tot)}\nVocê paga só de Juros: {formatar_moeda_visual(jur)} ⚠️"; j_res.color = "#f87171"; page.update()
            except: pass
        box_juros = ft.Container(content=ft.Column([ft.Text("Calculadora de Juros"), ft.Row([j_val, j_taxa, j_parc], wrap=True), ft.ElevatedButton("Calcular Juros", on_click=calc_juros, bgcolor="#f87171", color="white"), j_res]), bgcolor="#1e293b", padding=15, border_radius=10)

        t_dica = ft.Text("Dica Financeira (IA)", weight="bold", color=COR_PRINCIPAL); c_dica = ft.Text("", size=12)
        def carregar_dica(e): t_dica.value = "Consultando..."; page.update(); d_ia, cor = obter_dica_ia(); t_dica.value, c_dica.value = d_ia; page.update()
        box_ia = ft.Container(content=ft.Column([ft.Row([t_dica, ft.IconButton(icon="auto_awesome", icon_color=COR_PRINCIPAL, on_click=carregar_dica)], alignment="spaceBetween"), c_dica]), bgcolor="#1e293b", padding=15, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, COR_PRINCIPAL)))

        t_agencia = ft.TextField(label="Ex: Pagar Net 120 dia 15", expand=True)
        def agendar_ia(e):
            d = interpretar_comando(t_agencia.value)
            if d:
                criar_lembrete(d.get('nome','Conta'), d.get('data',''), d.get('valor',0))
                t_agencia.value=""; notificar("Anotado!")
                try: page.launch_url(f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={urllib.parse.quote(d.get('nome','Conta'))}&details=Valor:{d.get('valor')}")
                except: pass
            else: notificar("Não entendi.", "red")
        box_agendador = ft.Container(content=ft.Column([ft.Text("Agendar boleto"), ft.Row([t_agencia, ft.IconButton(icon="auto_fix_high", icon_color=COR_PRINCIPAL, on_click=agendar_ia)])]), bgcolor="#1e293b", padding=15, border_radius=10)

        t_faq = ft.TextField(label="Pergunte...", expand=True); r_faq = ft.Text("")
        def perguntar(e):
            if not TEM_IA: r_faq.value = "Tô offline 😴"; return
            r_faq.value = "Pensando..."; page.update(); txt = chamar_gemini(f"Responda curto: {t_faq.value}"); r_faq.value = txt if txt else "Erro."; page.update()
        box_faq = ft.Container(content=ft.Column([ft.Text("Dúvida Inteligente", weight="bold"), ft.Row([t_faq, ft.IconButton(icon="send", on_click=perguntar)]), r_faq]), bgcolor="#1e293b", padding=15, border_radius=10)

        def doar(e): page.set_clipboard("SUA_CHAVE_PIX_AQUI"); notificar("Pix Copiado! Valeu pelo café ☕")
        box_doar = ft.Container(content=ft.Row([ft.ElevatedButton("Doar Café ☕", on_click=doar, bgcolor="#fbbf24", color="black")]), bgcolor="#1e293b", padding=15, border_radius=10)

        return ft.Container(padding=ft.padding.only(left=20, right=20, top=20, bottom=20), content=ft.Column([
            ft.Text("Ferramentas", size=24, weight="bold"), box_perfil, ft.Container(height=10),
            box_troco, ft.Container(height=10), box_juros, ft.Container(height=10),
            box_ia, ft.Container(height=10), box_agendador, ft.Container(height=10),
            box_faq, ft.Container(height=10), box_doar, ft.Container(height=20), barra_simbolos()], scroll="auto"), expand=True)

    # --- MENU GAVETA ---
    page.drawer = ft.NavigationDrawer(bgcolor="#1e293b", indicator_color=COR_PRINCIPAL, controls=[
        ft.Container(height=20), ft.Text("  FINANTEA", size=20, weight="bold", color="white"), ft.Divider(color="grey"),
        ft.NavigationDrawerDestination(label="Extrato", icon="list"),
        ft.NavigationDrawerDestination(label="Meus Objetivos", icon="savings"),
        ft.NavigationDrawerDestination(label="Ferramentas", icon="build"),
    ], on_change=lambda e: (mudar(e.control.selected_index), page.close_drawer()))

    def abrir_menu(e): page.drawer.open = True; page.update()
    page.appbar = ft.AppBar(leading=ft.IconButton(icon="menu", on_click=abrir_menu), title=ft.Text("Finantea"), bgcolor="#0f172a")
    page.add(conteudo)

    if not is_intro_ok(): conteudo.content = tela_onboarding()
    else: conteudo.content = tela_extrato()
    page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
