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

# SOLUÇÃO DE PERSISTÊNCIA PARA ANDROID/APK
try:
    caminho_raiz = os.getcwd()
    DB_NAME = os.path.join(caminho_raiz, "dados_financeiros.db")
    PASTA_COMPROVANTES = os.path.join(caminho_raiz, "comprovantes")
    if not os.path.exists(PASTA_COMPROVANTES):
        os.makedirs(PASTA_COMPROVANTES)
    print(f"Banco de dados definido em: {DB_NAME}") 
except Exception as e:
    print(f"Erro ao definir caminhos: {e}")
    DB_NAME = "dados_financeiros.db"

# ==============================================================================
# 1. CÉREBRO DA AUTIAH (CONFIGURAÇÃO DE PERSONA & CONTEXTO)
# ==============================================================================
API_KEY = os.getenv("API_KEY")
TEM_IA = bool(API_KEY)

CONTEXTO_APP = """
VOCÊ É A AUTIAH: A IA integrada ao app Finantea.
O Finantea é um organizador financeiro para neurodivergentes (TDAH/Autismo), NÃO é um banco real.

SUAS INSTRUÇÕES SOBRE AS FERRAMENTAS DO APP:
1. Agendar Boleto (A Varinha Mágica): O usuário digita texto natural (ex: "Luz 100 dia 15"). O app apenas SALVA NO BANCO DE DADOS e gera um LINK PARA O GOOGLE AGENDA. O app NÃO paga a conta sozinho.
2. Preço de Vida: Calcula quanto custa um item em "horas de trabalho" baseado na renda do usuário.
3. Caçador de Assinaturas: Uma lista separada para gastos recorrentes.
4. Extrato: Registro de receitas e despesas.

REGRA DE RESPOSTA:
- Se perguntarem "Como funciona?", explique a função específica.
- Jamais diga que o app faz pagamentos bancários reais.
- Seja literal, direta e acolhedora.
"""

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

# --- CRUD Operations ---
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

def criar_lembrete(n, d, v): cursor.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status) VALUES (?, ?, ?, 'Pendente')", (n, d, v)); conn.commit()
def set_renda(valor): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (valor,)); conn.commit()
def get_renda(): cursor.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = cursor.fetchone(); return res[0] if res else 0.0
def set_intro_ok(): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); conn.commit()
def is_intro_ok(): cursor.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = cursor.fetchone(); return True if res and res[0] == 1 else False

def adicionar_assinatura(nome, valor): cursor.execute("INSERT INTO assinaturas (nome, valor, em_uso) VALUES (?, ?, 1)", (nome, valor)); conn.commit()
def listar_assinaturas(): cursor.execute("SELECT * FROM assinaturas"); return cursor.fetchall()
def toggle_uso_assinatura(id_ass, status_atual): 
    novo = 0 if status_atual == 1 else 1
    cursor.execute("UPDATE assinaturas SET em_uso = ? WHERE id = ?", (novo, id_ass)); conn.commit()
def deletar_assinatura(id_ass): cursor.execute("DELETE FROM assinaturas WHERE id = ?", (id_ass,)); conn.commit()

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

# ==============================================================================
# 3. INTERFACE (V49 - FINAL ESTÁVEL)
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

    def obter_dica_autiah():
        if not TEM_IA: return ("Autiah Offline", "Verifique sua internet ou chave."), "grey"
        renda = get_renda()
        cursor.execute("SELECT SUM(valor) FROM financeiro"); saldo = cursor.fetchone()[0] or 0
        prompt = f"Aja como Autiah. Renda {renda:.2f}, Saldo {saldo:.2f}. Dica de 1 frase."
        txt = chamar_autiah(prompt)
        return ("Dica da Autiah:", txt) if txt else ("Erro", "Tente novamente."), COR_PRINCIPAL

    def barra_simbolos():
        return ft.Container(content=ft.Row([
            ft.Tooltip(message="Autismo", content=ft.Icon(ft.icons.EXTENSION, color="#007ACC")),
            ft.Tooltip(message="Deficiências Ocultas", content=ft.Icon(ft.icons.WB_SUNNY, color="#fbbf24")),
            ft.Tooltip(message="Neurodiversidade", content=ft.Icon(ft.icons.ALL_INCLUSIVE, color="red")),
        ], alignment="center", spacing=20), padding=20)

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
        def acao_pular(e): set_intro_ok(); notificar("Configuração pulada."); mudar(0)
        return ft.Container(alignment=ft.alignment.center, content=ft.Column([
            ft.Icon("rocket_launch", size=60, color=COR_PRINCIPAL),
            ft.Text("Bem-vindo ao Finantea!", size=24, weight="bold"),
            t_renda,
            ft.ElevatedButton("Iniciar", bgcolor=COR_PRINCIPAL, color="white", width=200, height=50, on_click=acao_comecar),
            ft.TextButton("Pular por enquanto", on_click=acao_pular),
            ft.Container(height=30), barra_simbolos()
        ], alignment="center", horizontal_alignment="center"))

    # --- TELA 1: EXTRATO ---
    def tela_extrato():
        lista = ft.Column(scroll="auto", expand=True)
        t_data = ft.TextField(label="Quando?", value=datetime.now().strftime("%d/%m/%Y"), width=100)
        t_desc = ft.TextField(label="Com o que?", expand=True)
        t_val = ft.TextField(label="Quanto?", width=150, keyboard_type="number", on_change=mascara_dinheiro)
        t_tipo = ft.Dropdown(width=100, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")
        
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
            if arq: 
                notificar(f"PDF salvo em {arq}")
                try: page.launch_url(arq)
                except: pass

        dd_mes.on_change = lambda e: render()
        btn_add = ft.ElevatedButton("Salvar", bgcolor=COR_PRINCIPAL, color="white", on_click=salvar)
        btn_pdf = ft.IconButton(icon="picture_as_pdf", icon_color=COR_PRINCIPAL, on_click=criar_pdf)
        render()
        return ft.Container(padding=10, content=ft.Column([
            ft.Row([ft.Text("Extrato Mensal", size=24, weight="bold"), ft.Row([dd_mes, btn_pdf], spacing=10)], alignment="spaceBetween"),
            ft.Container(content=ft.Column([ft.Row([txt_ganhou, txt_gastou], alignment="spaceBetween"), ft.Divider(color="grey"), ft.Row([txt_saldo], alignment="center")]), bgcolor="#1e293b", padding=15, border_radius=10, border=ft.border.all(1, "#334155")),
            ft.Container(height=10), lista,
            ft.Container(content=ft.Column([ft.Text("Novo Lançamento", weight="bold"), ft.Row([t_data, t_tipo, t_val]), ft.Row([t_desc]), btn_add]), bgcolor="#1e293b", padding=15, border_radius=10)
        ], expand=True))

    # --- TELA 2: FERRAMENTAS ---
    def tela_ferramentas():
        t_renda = ft.TextField(label="Renda Mensal", value=formatar_moeda_visual(get_renda()), width=150, on_change=mascara_dinheiro)
        def salvar_renda(e): set_renda(limpar_valor(t_renda.value)); notificar("Renda atualizada."); tela_ferramentas()
        box_perfil = ft.Container(content=ft.Row([t_renda, ft.ElevatedButton("Atualizar", on_click=salvar_renda)]), bgcolor="#1e293b", padding=15, border_radius=10)

        # Preço de Vida
        renda_atual = get_renda()
        hora_trabalho = renda_atual / 160 if renda_atual > 0 else 0
        t_preco_item = ft.TextField(label="Preço do Item", prefix_text="R$ ", on_change=mascara_dinheiro, expand=True)
        txt_resultado_vida = ft.Text("Digite um valor...", italic=True)
        def calc_vida(e):
            val = limpar_valor(t_preco_item.value)
            if hora_trabalho <= 0: txt_resultado_vida.value = "Defina sua renda primeiro!"; txt_resultado_vida.color="red"
            else:
                horas_custo = val / hora_trabalho
                if horas_custo < 1: txt_resultado_vida.value = f"Custo: {int(horas_custo*60)} minutos de trabalho."
                elif horas_custo < 8: txt_resultado_vida.value = f"Custo: {horas_custo:.1f} horas de trabalho."
                else: txt_resultado_vida.value = f"Custo: {horas_custo/8:.1f} DIAS de trabalho."
                txt_resultado_vida.color = COR_PRINCIPAL
            page.update()
        box_preco_vida = ft.Container(content=ft.Column([ft.Text("Preço de Vida (Abstração)", weight="bold", size=16), ft.Text(f"Sua hora vale: {formatar_moeda_visual(hora_trabalho)}", size=12, color="grey"), ft.Row([t_preco_item, ft.IconButton(icon="calculate", on_click=calc_vida, icon_color=COR_PRINCIPAL)]), txt_resultado_vida]), bgcolor="#1e293b", padding=15, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, "#fbbf24")))

        # Troco e Juros
        t_tot = ft.TextField(label="Total Compra", width=120, on_change=mascara_dinheiro); t_pag = ft.TextField(label="Valor Pago", width=120, on_change=mascara_dinheiro); res = ft.Text("Troco: R$ 0,00", size=16, weight="bold")
        def calc_troco(e): tr = limpar_valor(t_pag.value) - limpar_valor(t_tot.value); res.value = f"Troco: {formatar_moeda_visual(tr)}"; res.color = "green" if tr >= 0 else "red"; page.update()
        box_troco = ft.Container(content=ft.Column([ft.Text("Calculadora de Troco"), ft.Row([t_tot, t_pag, ft.ElevatedButton("=", on_click=calc_troco)]), res]), bgcolor="#1e293b", padding=15, border_radius=10)

        j_val = ft.TextField(label="Valor Compra", width=120, on_change=mascara_dinheiro); j_taxa = ft.TextField(label="Juros (%)", width=120); j_parc = ft.TextField(label="Parcelas", width=80); j_res = ft.Text("Vale a pena parcelar?", color="grey")
        def calc_juros(e):
            try:
                v = limpar_valor(j_val.value); i = float(j_taxa.value.replace(",", "."))/100; n = int(j_parc.value)
                tot = v * ((1+i)**n); jur = tot - v
                j_res.value = f"Total Final: {formatar_moeda_visual(tot)}\nVocê paga só de Juros: {formatar_moeda_visual(jur)} ⚠️"; j_res.color = "#f87171"; page.update()
            except: pass
        box_juros = ft.Container(content=ft.Column([ft.Text("Calculadora de Juros"), ft.Row([j_val, j_taxa, j_parc], wrap=True), ft.ElevatedButton("Calcular Juros", on_click=calc_juros, bgcolor="#f87171", color="white"), j_res]), bgcolor="#1e293b", padding=15, border_radius=10)

        # Autiah
        t_dica = ft.Text("Dica da Autiah", weight="bold", color=COR_PRINCIPAL); c_dica = ft.Text("", size=12)
        def carregar_dica(e): t_dica.value = "Autiah pensando..."; page.update(); d_ia, cor = obter_dica_autiah(); t_dica.value, c_dica.value = d_ia; page.update()
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

        t_faq = ft.TextField(label="Fale com a Autiah...", expand=True); r_faq = ft.Text("")
        def perguntar(e):
            if not TEM_IA: r_faq.value = "Estou offline."; return
            r_faq.value = "Digitando..."; page.update()
            prompt_completo = f"{CONTEXTO_APP}\n\nPERGUNTA DO USUÁRIO: {t_faq.value}"
            txt = chamar_autiah(prompt_completo)
            r_faq.value = txt if txt else "Erro."; page.update()
        box_faq = ft.Container(content=ft.Column([ft.Text("Chat com Autiah", weight="bold"), ft.Row([t_faq, ft.IconButton(icon="send", on_click=perguntar)]), r_faq]), bgcolor="#1e293b", padding=15, border_radius=10)

        return ft.Container(padding=10, content=ft.Column([
            ft.Text("Ferramentas", size=24, weight="bold"), box_perfil, ft.Container(height=10),
            box_preco_vida, ft.Container(height=10), box_troco, ft.Container(height=10), box_juros, ft.Container(height=10),
            box_ia, ft.Container(height=10), box_agendador, ft.Container(height=10), box_faq, ft.Container(height=20),
            barra_simbolos()], scroll="auto"), expand=True)

    # --- TELA 3: ASSINATURAS ---
    def tela_assinaturas():
        lista_ass = ft.Column(expand=True, scroll="auto")
        t_nome_ass = ft.TextField(label="Nome (ex: Netflix)", expand=True)
        t_val_ass = ft.TextField(label="Valor", width=100, on_change=mascara_dinheiro)
        def render_ass():
            lista_ass.controls.clear()
            assinaturas = listar_assinaturas()
            total_recorrente = sum(a[2] for a in assinaturas)
            lista_ass.controls.append(ft.Container(content=ft.Text(f"Total Recorrente: {formatar_moeda_visual(total_recorrente)}/mês", weight="bold", color="white"), bgcolor="#334155", padding=10, border_radius=5))
            for a in assinaturas:
                id_ass, nome, valor, em_uso = a
                cor_status = "#4ade80" if em_uso else "#f87171"
                txt_status = "Em uso" if em_uso else "CANCELAR?"
                def acao_toggle(e, x=id_ass, s=em_uso): toggle_uso_assinatura(x, s); render_ass(); page.update()
                def acao_del(e, x=id_ass): deletar_assinatura(x); render_ass(); page.update()
                lista_ass.controls.append(ft.Container(content=ft.Row([
                    ft.Column([ft.Text(nome, weight="bold"), ft.Text(formatar_moeda_visual(valor), size=12)], expand=True),
                    ft.Column([ft.Text(txt_status, color=cor_status, weight="bold", size=12), ft.IconButton(icon=ft.icons.THUMB_UP if em_uso else ft.icons.THUMB_DOWN, icon_color=cor_status, on_click=acao_toggle)], alignment="center"),
                    ft.IconButton(icon="delete", icon_color="grey", on_click=acao_del)
                ]), bgcolor="#1e293b", padding=10, border_radius=10, border=ft.border.only(left=ft.border.BorderSide(4, cor_status))))
        def add_ass(e):
            val = limpar_valor(t_val_ass.value)
            if not t_nome_ass.value or val <= 0: notificar("Dados inválidos", "red"); return
            adicionar_assinatura(t_nome_ass.value, val); t_nome_ass.value = ""; t_val_ass.value = ""; render_ass(); page.update()
        render_ass()
        return ft.Container(padding=10, content=ft.Column([
            ft.Text("Caçador de Assinaturas", size=24, weight="bold"), ft.Container(height=10), lista_ass,
            ft.Container(content=ft.Row([t_nome_ass, t_val_ass, ft.IconButton(icon="add_circle", icon_color=COR_PRINCIPAL, icon_size=40, on_click=add_ass)]), bgcolor="#1e293b", padding=10, border_radius=10)
        ], expand=True))

    # --- MENU DE NAVEGAÇÃO ---
    def navegar(e):
        idx = e.control.selected_index
        if idx == 3: # BOTÃO DOAR
            page.set_clipboard("85996994887")
            notificar("Pix copiado! Espero que não faça falta.", "#32bcad")
            page.drawer.open = False; page.update(); return
        mudar(idx); page.drawer.open = False; page.update()

    page.drawer = ft.NavigationDrawer(bgcolor="#1e293b", indicator_color=COR_PRINCIPAL, controls=[
        ft.Container(height=20), ft.Text("  FINANTEA", size=20, weight="bold", color="white"), ft.Divider(color="grey"),
        ft.NavigationDrawerDestination(label="Extrato", icon="list"),
        ft.NavigationDrawerDestination(label="Ferramentas & Cálculos", icon="calculate"),
        ft.NavigationDrawerDestination(label="Caçador de Assinaturas", icon="subscriptions"),
        ft.Divider(color="grey"),
        ft.NavigationDrawerDestination(label="Doar Café pro Autista", icon_content=ft.Icon(ft.icons.COFFEE, color="#fbbf24")),
    ], on_change=navegar)

    def abrir_menu(e): page.drawer.open = True; page.update()
    page.appbar = ft.AppBar(leading=ft.IconButton(icon="menu", on_click=abrir_menu), title=ft.Text("Finantea"), bgcolor="#0f172a", elevation=0)
    
    page.add(ft.SafeArea(conteudo, expand=True))
    if not is_intro_ok(): conteudo.content = tela_onboarding()
    else: conteudo.content = tela_extrato()
    page.update()

if __name__ == "__main__":
    ft.app(target=main)
carregar_env_manual()

# ==============================================================================
# 1. CÉREBRO DA AUTIAH (VIA HTTP - SEM INSTALAR NADA)
# ==============================================================================
API_KEY = os.getenv("API_KEY", "") 
TEM_IA = True

def chamar_autiah(prompt_usuario):
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
        # Caminho absoluto para garantir leitura no Android
        db_path = os.path.join(os.getcwd(), DB_NAME)
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
# 4. INTERFACE (CORREÇÃO DE ERRO PREFIX_TEXT)
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
            # CORREÇÃO: Substituído 'prefix_text' (quebra no Android) por 'prefix' (seguro)
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
                    # CORREÇÃO: icon="name"
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

            # Preço de Vida (CORREÇÃO PREFIX)
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
                # CORREÇÃO: icon="name"
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
                        # CORREÇÃO: icon="name"
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
                # CORREÇÃO: icon="name"
                ft.Container(content=ft.Row([t_nome, t_val, ft.IconButton(icon="add_circle", icon_color=COR_PRINCIPAL, icon_size=40, on_click=add)]), bgcolor="#1e293b", padding=10, border_radius=10),
                ft.Container(height=50)
            ])

        # Navegação
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
            # CORREÇÃO: icon="name"
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

