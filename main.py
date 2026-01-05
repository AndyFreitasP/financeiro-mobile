import flet as ft
import sqlite3
from datetime import datetime, timedelta
from fpdf import FPDF
import os
import random
import google.generativeai as genai
import json
import urllib.parse

# ==============================================================================
# CONFIGURAÇÃO GERAL
# ==============================================================================
DB_NAME = "dados_financeiros.db"
UPLOAD_DIR = "comprovantes"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# ==============================================================================
# 1. CONFIGURAÇÃO IA (GEMINI PRO)
# ==============================================================================
API_KEY = "AIzaSyBtR6YjyGJLD-KY6jQoFpKyBZHMSH_PEnE" 
MODELO_USADO = None
TEM_IA = False

def configurar_ia():
    global MODELO_USADO, TEM_IA
    try:
        genai.configure(api_key=API_KEY)
        MODELO_USADO = genai.GenerativeModel('gemini-pro')
        TEM_IA = True
        print("IA Conectada: Gemini Pro")
    except Exception as e:
        print(f"Erro IA: {e}")

configurar_ia()

# ==============================================================================
# 2. DICAS & BACKUPS
# ==============================================================================
DICAS_OFFLINE = [
    ("Modo Offline", "Sem conexão com a IA. Use os campos manuais abaixo."),
    ("Dica Rápida", "Use o microfone do seu teclado para ditar as contas."),
]

# ==============================================================================
# 3. ENGINE DE RELATÓRIOS
# ==============================================================================
class RelatorioPDF(FPDF):
    def __init__(self, titulo="RELATÓRIO FINANTEA"):
        super().__init__()
        self.titulo_doc = titulo
    def header(self):
        self.set_fill_color(0, 122, 204); self.rect(0, 0, 210, 35, 'F'); self.set_y(10)
        self.set_font('Arial', 'B', 18); self.set_text_color(255, 255, 255); self.cell(0, 10, self.titulo_doc, 0, 1, 'C')
        self.set_font('Arial', '', 9); self.cell(0, 5, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C'); self.ln(20)
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8); self.set_text_color(128); self.cell(0, 10, 'FINANTEA - Powered by AndyP', 0, 0, 'C')

def gerar_relatorio_contas(contas, tipo_relatorio):
    pdf = RelatorioPDF(f"RELATÓRIO DE CONTAS - {tipo_relatorio}"); pdf.add_page()
    for conta in contas:
        try: nome, data, valor, status = conta[1], conta[2], conta[3], conta[4]
        except: continue 
        pdf.set_font("Arial", "B", 12); pdf.set_text_color(0, 0, 0); pdf.cell(0, 8, f"{nome} - {status}", ln=True)
        pdf.set_font("Arial", "", 10); pdf.set_text_color(50, 50, 50); pdf.cell(50, 6, f"Vencimento: {data}", 0, 0); pdf.cell(50, 6, f"Valor: R$ {valor:.2f}", 0, 1)
        pdf.ln(5); pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5)
    nome_arquivo = f"relatorio_{tipo_relatorio.lower()}.pdf"; pdf.output(nome_arquivo); return nome_arquivo

def gerar_pdf_financeiro(dados, saldo_total, mes_referencia):
    cor_tema = (46, 204, 113) if saldo_total >= 0 else (231, 76, 60)
    pdf = RelatorioPDF("EXTRATO MENSAL"); pdf.add_page(); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, txt=f"Referência: {mes_referencia}", ln=True)
    pdf.set_font("Arial", "B", 14); pdf.write(8, "Saldo Final: "); pdf.set_text_color(*cor_tema); pdf.write(8, f"R$ {saldo_total:,.2f}"); pdf.ln(15)
    pdf.set_fill_color(240, 240, 240); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "B", 10)
    pdf.cell(30, 10, "Data", 1, 0, 'C', 1); pdf.cell(100, 10, "Descrição", 1, 0, 'L', 1); pdf.cell(40, 10, "Valor", 1, 1, 'R', 1); pdf.set_font("Arial", "", 10)
    for row in dados:
        data, desc, valor = row[1], row[2], row[5]
        pdf.set_text_color(0, 0, 0); pdf.cell(30, 8, data, 1, 0, 'C'); pdf.set_text_color(50, 50, 50); pdf.cell(100, 8, f" {desc[:45]}", 1, 0, 'L')
        if valor < 0: pdf.set_text_color(231, 76, 60)
        else: pdf.set_text_color(46, 204, 113)
        pdf.cell(40, 8, f"R$ {valor:.2f} ", 1, 1, 'R')
    nome_arquivo = f"extrato_{mes_referencia.replace('/', '_')}.pdf"; pdf.output(nome_arquivo); return nome_arquivo

# ==============================================================================
# 4. LÓGICA PRINCIPAL DO APP
# ==============================================================================
def main(page: ft.Page):
    page.title = "FINANTEA" 
    page.theme_mode = "dark" 
    page.bgcolor = "#000000"
    page.padding = 0
    page.window_width = 400  
    page.window_height = 800
    
    # --- BANCO DE DADOS ---
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS financeiro (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, categoria TEXT, tipo TEXT, valor REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS metas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, valor_alvo REAL, valor_atual REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS lembretes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, data_vencimento TEXT, valor REAL, status TEXT DEFAULT 'Pendente', anexo TEXT)")
        # Tabela PERFIL para Renda e Configurações (intro_ok)
        cursor.execute("CREATE TABLE IF NOT EXISTS perfil (id INTEGER PRIMARY KEY, tipo TEXT UNIQUE, valor REAL)")
        conn.commit()
    except Exception as e:
        page.add(ft.Text(f"Erro BD: {e}", color="red")); return

    # --- HELPERS FORMATAÇÃO (MÁSCARAS) ---
    def formatar_data(e):
        valor = "".join(filter(str.isdigit, e.control.value))[:8]
        if len(valor) > 4: e.control.value = f"{valor[:2]}/{valor[2:4]}/{valor[4:]}"
        elif len(valor) > 2: e.control.value = f"{valor[:2]}/{valor[2:]}"
        else: e.control.value = valor
        e.control.update()

    def formatar_moeda(e):
        valor = "".join(filter(str.isdigit, e.control.value))
        if not valor: e.control.value = ""
        else: e.control.value = f"{int(valor)/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        e.control.update()

    # --- FUNÇÕES BD ---
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
    def criar_meta(n, a): cursor.execute("INSERT INTO metas (nome, valor_alvo, valor_atual) VALUES (?, ?, 0)", (n, a)); conn.commit()
    def atualizar_meta(idm, v): cursor.execute("UPDATE metas SET valor_atual = valor_atual + ? WHERE id = ?", (v, idm)); conn.commit()
    def listar_metas(): cursor.execute("SELECT * FROM metas"); return cursor.fetchall()
    def deletar_meta(idm): cursor.execute("DELETE FROM metas WHERE id = ?", (idm,)); conn.commit()
    def criar_lembrete(n, d, v): cursor.execute("INSERT INTO lembretes (nome, data_vencimento, valor, status, anexo) VALUES (?, ?, ?, 'Pendente', NULL)", (n, d, v)); conn.commit()
    def listar_lembretes_filtro(pagos=False):
        s = 'Pago' if pagos else 'Pendente'; o = 'DESC' if pagos else 'ASC'
        cursor.execute(f"SELECT * FROM lembretes WHERE status = ? ORDER BY id {o}", (s,)); return cursor.fetchall()
    def marcar_como_pago(idl): cursor.execute("UPDATE lembretes SET status = 'Pago' WHERE id = ?", (idl,)); conn.commit()
    def deletar_lembrete(idl): cursor.execute("DELETE FROM lembretes WHERE id = ?", (idl,)); conn.commit()
    
    # PERFIL/RENDA & INTRO
    def set_renda(valor): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (1, 'renda', ?)", (valor,)); conn.commit()
    def get_renda(): cursor.execute("SELECT valor FROM perfil WHERE tipo='renda'"); res = cursor.fetchone(); return res[0] if res else 0.0
    
    def set_intro_ok(): cursor.execute("INSERT OR REPLACE INTO perfil (id, tipo, valor) VALUES (2, 'intro_ok', 1)"); conn.commit()
    def is_intro_ok(): cursor.execute("SELECT valor FROM perfil WHERE tipo='intro_ok'"); res = cursor.fetchone(); return True if res and res[0] == 1 else False

    # --- GOOGLE AGENDA ---
    def abrir_google_agenda(e, nome, data, valor):
        try:
            dt_obj = datetime.strptime(data, "%d/%m/%Y"); data_fmt = dt_obj.strftime("%Y%m%d")
            detalhes = f"Valor: R$ {valor:.2f}. Criado pelo Finantea."
            url = f"https://www.google.com/calendar/render?action=TEMPLATE&text={urllib.parse.quote(nome)}&dates={data_fmt}/{data_fmt}&details={urllib.parse.quote(detalhes)}"
            page.launch_url(url)
        except: page.snack_bar = ft.SnackBar(ft.Text("Erro na data."), bgcolor="red"); page.snack_bar.open=True; page.update()

    # --- CÉREBRO IA ---
    def interpretar_comando_ia(texto):
        if not TEM_IA: return None, "Estou offline. Preencha manualmente."
        hoje = datetime.now().strftime("%d/%m/%Y")
        prompt = f"""
        Você é o cérebro do app Finantea. Hoje é {hoje}.
        Texto do usuário: "{texto}"
        Retorne APENAS um JSON puro (sem ```json) com: "nome", "valor" (float), "data" (dd/mm/aaaa). Se faltar algo, mande null.
        """
        try:
            res = MODELO_USADO.generate_content(prompt)
            texto_limpo = res.text.strip().replace("```json", "").replace("```", "")
            return json.loads(texto_limpo), None
        except Exception as e: return None, str(e)

    def obter_dica_ia():
        if not TEM_IA: return ("Dica Offline", "Respire e organize uma coisa de cada vez."), "grey"
        cursor.execute("SELECT SUM(valor) FROM financeiro"); saldo = cursor.fetchone()[0] or 0
        renda = get_renda()
        prompt = f"""
        Aja como o 'Finantea', um consultor financeiro amigo.
        Dados: Saldo R$ {saldo:.2f}. Renda Mensal R$ {renda:.2f}.
        Me dê UMA dica curta (max 15 palavras) e motivadora.
        """
        try: 
            res = MODELO_USADO.generate_content(prompt)
            return ("Dica Finantea", res.text), "#007ACC"
        except: return ("Dica Offline", "Foco no essencial."), "grey"

    def obter_ajuda_ia(pergunta):
        if not TEM_IA: return "Estou offline no momento."
        cursor.execute("SELECT COUNT(*) FROM lembretes WHERE status='Pendente'"); pendentes = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(valor) FROM financeiro"); saldo = cursor.fetchone()[0] or 0
        renda = get_renda()
        manual = "MANUAL: O Raio (Varinha) preenche automático. Apagar da Agenda Google é manual."
        prompt = f"""
        Suporte Técnico Finantea.
        Dados: Saldo R$ {saldo:.2f}, Renda R$ {renda:.2f}, Contas Pendentes: {pendentes}.
        {manual}
        Pergunta: "{pergunta}"
        Responda curto (máx 2 frases).
        """
        try: res = MODELO_USADO.generate_content(prompt); return res.text
        except: return "Erro ao processar."

    # --- UI COMPONENTES (TELAS DO APP) ---
    conteudo_principal = ft.Container(expand=True, padding=10)
    
    # 1. TELA DE INTRODUÇÃO (ONBOARDING CORRIGIDO V40)
    def tela_intro():
        txt_renda_intro = ft.TextField(label="Qual sua Renda Mensal aproximada?", hint_text="R$ 0,00", text_size=16, keyboard_type="number", on_change=formatar_moeda, width=280)
        
        def salvar_e_entrar(e):
            try:
                v = float(txt_renda_intro.value.replace(".","").replace(",", "."))
                set_renda(v)
                set_intro_ok()
                ir_para_app()
            except:
                txt_renda_intro.error_text = "Digite um valor válido"
                txt_renda_intro.update()

        def pular_intro(e):
            def fechar_dlg(e): page.dialog.open = False; page.update(); set_intro_ok(); ir_para_app()
            dlg = ft.AlertDialog(
                title=ft.Text("Tem certeza?"),
                content=ft.Text("Cadastrar a renda ajuda a IA a dar dicas melhores. Mas você pode fazer isso depois na aba Ferramentas."),
                actions=[ft.TextButton("Entendi, vamos lá!", on_click=fechar_dlg)]
            )
            page.dialog = dlg; dlg.open = True; page.update()

        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.ROCKET_LAUNCH, size=60, color="#007ACC"),
                ft.Text("Bem-vindo ao Finantea!", size=24, weight="bold"),
                ft.Text("Vamos configurar seu perfil para a IA te ajudar melhor.", text_align="center", color="grey"),
                ft.Divider(height=20, color="transparent"),
                txt_renda_intro,
                ft.ElevatedButton("Salvar e Começar", bgcolor="#007ACC", color="white", width=200, height=45, on_click=salvar_e_entrar),
                ft.TextButton("Pular por enquanto", on_click=pular_intro)
            ], alignment="center", horizontal_alignment="center", spacing=15),
            alignment=ft.Alignment(0, 0), # CORREÇÃO AQUI (V40)
            expand=True
        )

    # 2. TELAS DO APP PRINCIPAL
    def tela_extrato():
        lista = ft.Column(spacing=10, scroll="auto", expand=True)
        txt_saldo = ft.Text("R$ 0,00", size=30, weight="bold")
        meses = get_meses(); mes_atual = f"{datetime.now().month:02d}/{datetime.now().year}"
        if mes_atual not in meses: meses.append(mes_atual)
        dd_mes = ft.Dropdown(width=120, bgcolor="#111", border_radius=10, options=[ft.dropdown.Option(m) for m in meses], value=mes_atual)
        
        t_data = ft.TextField(label="Data", value=datetime.now().strftime("%d/%m/%Y"), bgcolor="#111", expand=1, on_change=formatar_data)
        t_tipo = ft.Dropdown(bgcolor="#111", expand=1, options=[ft.dropdown.Option("Despesa"), ft.dropdown.Option("Receita")], value="Despesa")
        t_desc = ft.TextField(label="Descrição", bgcolor="#111", expand=2)
        t_val = ft.TextField(label="Valor", bgcolor="#111", keyboard_type="number", expand=1, on_change=formatar_moeda)
        t_cat = ft.TextField(label="Categoria", bgcolor="#111")

        def atualizar(e=None):
            dados = listar(dd_mes.value); lista.controls.clear()
            saldo = sum(row[5] for row in dados)
            if not dados: lista.controls.append(ft.Text("Sem registros.", color="grey"))
            for r in dados:
                cor = "#FF5555" if r[5] < 0 else "#00FF7F"
                btn_del = ft.IconButton(ft.Icons.DELETE, icon_color="#444", tooltip="Apagar registro", on_click=lambda e, x=r[0]: (deletar(x), atualizar()))
                lista.controls.append(ft.Container(content=ft.Row([ft.Column([ft.Text(r[1][:5], weight="bold"), ft.Text(r[3], size=10, color="grey")]), ft.Text(r[2], expand=True), ft.Column([ft.Text(f"R$ {r[5]:.2f}", color=cor, weight="bold"), btn_del])]), bgcolor="#111", padding=10, border_radius=10, border=ft.Border(left=ft.BorderSide(4, cor))))
            txt_saldo.value = f"R$ {saldo:,.2f}"; txt_saldo.color = "#FF5555" if saldo < 0 else "#00FF7F"; page.update()

        def add(e):
            try: adicionar(t_data.value, t_desc.value, t_cat.value, t_tipo.value, float(t_val.value.replace(".","").replace(",","."))); t_desc.value=""; t_val.value=""; atualizar()
            except: pass
        
        dd_mes.on_change = atualizar; btn_add = ft.ElevatedButton("Lançar", bgcolor="#007ACC", color="white", on_click=add)
        btn_pdf = ft.IconButton(ft.Icons.PICTURE_AS_PDF, icon_color="#007ACC", tooltip="Gerar PDF", on_click=lambda e: os.startfile(gerar_pdf_financeiro(listar(dd_mes.value), sum(r[5] for r in listar(dd_mes.value)), dd_mes.value)))

        layout = ft.Column([ft.Row([ft.Text("HISTÓRICO", weight="bold"), ft.Row([dd_mes, btn_pdf])], alignment="spaceBetween"), ft.Container(content=txt_saldo, padding=15, bgcolor="#111", border_radius=15), lista, ft.ExpansionTile(title=ft.Text("Novo Lançamento", size=14), controls=[ft.Column([ft.Row([t_data, t_tipo]), ft.Row([t_desc, t_val]), t_cat, btn_add])])], expand=True)
        atualizar(); return layout

    def tela_cofrinho():
        lista = ft.Column(spacing=10, scroll="auto", expand=True)
        def at(e=None):
            lista.controls.clear()
            for m in listar_metas():
                prog = m[3] / m[2] if m[2] > 0 else 0; cor = "#00FF7F" if prog >= 1 else "#007ACC"
                dep = ft.TextField(label="R$", width=70, height=35, text_size=12, on_change=formatar_moeda)
                btn_d = ft.TextButton("Depositar", on_click=lambda e, x=m[0], d=dep: (atualizar_meta(x, float(d.value.replace(".","").replace(",","."))), at()) if d.value else None)
                btn_x = ft.IconButton(ft.Icons.DELETE, icon_color="red", tooltip="Apagar Meta", on_click=lambda e, x=m[0]: (deletar_meta(x), at()))
                lista.controls.append(ft.Container(content=ft.Column([ft.Row([ft.Text(m[1], weight="bold"), btn_x], alignment="spaceBetween"), ft.ProgressBar(value=min(prog, 1), color=cor, bgcolor="#222"), ft.Row([ft.Text(f"R$ {m[3]:.0f}"), ft.Text(f"{int(prog*100)}%", color=cor)], alignment="spaceBetween"), ft.Row([dep, btn_d], alignment="end")]), bgcolor="#111", padding=15, border_radius=10))
            page.update()
        tn = ft.TextField(label="Meta"); ta = ft.TextField(label="Valor Alvo", on_change=formatar_moeda)
        b_c = ft.ElevatedButton("Criar Meta", on_click=lambda e: (criar_meta(tn.value, float(ta.value.replace(".","").replace(",","."))), at())); at()
        return ft.Column([ft.Text("COFRINHOS", weight="bold"), lista, ft.ExpansionTile(title=ft.Text("Nova Meta"), controls=[tn, ta, b_c])], expand=True)

    def tela_ferramentas():
        # 1. PERFIL
        txt_renda = ft.TextField(label="Renda Mensal (R$)", value=f"{get_renda():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), width=150, text_size=12, on_change=formatar_moeda)
        def salvar_renda_btn(e):
            try: set_renda(float(txt_renda.value.replace(".","").replace(",","."))); page.snack_bar = ft.SnackBar(ft.Text("Renda atualizada!")); page.snack_bar.open=True; page.update()
            except: pass
        bloco_perfil = ft.ExpansionTile(title=ft.Text("👤 Meu Perfil Financeiro", weight="bold", color="#00FF7F"), controls=[ft.Container(content=ft.Row([txt_renda, ft.ElevatedButton("Salvar", on_click=salvar_renda_btn)]), padding=10, bgcolor="#1A1A1A")])

        # 2. NEURO DICAS
        t_dica = ft.Text("Dica Neuro", weight="bold", color="#007ACC"); c_dica = ft.Text("Clique para gerar...", size=12, italic=True)
        barra_dica = ft.ProgressBar(width=None, color="#007ACC", bgcolor="#222", visible=False)
        def carregar_dica(e):
            btn_dica.disabled = True; btn_dica.icon = ft.Icons.HOURGLASS_TOP; barra_dica.visible = True; t_dica.value = "Pensando..."
            page.update()
            dados, cor = obter_dica_ia()
            t_dica.value = f"🤖 {dados[0]}"; t_dica.color = cor; c_dica.value = dados[1]; c_dica.italic = False
            btn_dica.disabled = False; btn_dica.icon = ft.Icons.AUTO_AWESOME; barra_dica.visible = False; page.update()
        btn_dica = ft.IconButton(icon=ft.Icons.AUTO_AWESOME, icon_color="#007ACC", tooltip="Nova Dica", on_click=carregar_dica)
        bloco_dicas = ft.Container(content=ft.Column([ft.Row([t_dica, btn_dica], alignment="spaceBetween"), barra_dica, c_dica]), bgcolor="#1A1A1A", padding=15, border_radius=10, border=ft.Border(left=ft.BorderSide(4, "#007ACC")))

        # 3. CALCULADORAS
        txt_total_compra = ft.TextField(label="Total", width=100, on_change=formatar_moeda); txt_valor_pago = ft.TextField(label="Pago", width=100, on_change=formatar_moeda)
        lbl_troco = ft.Text("Troco: R$ 0,00", weight="bold", size=16)
        def calc_troco(e):
            try: t = float(txt_valor_pago.value.replace(".","").replace(",", ".")) - float(txt_total_compra.value.replace(".","").replace(",", ".")); lbl_troco.value = f"Troco: R$ {t:.2f}"; lbl_troco.color = "#00FF7F" if t >= 0 else "red"
            except: lbl_troco.value = "Erro"; 
            page.update()
        
        lista_gastos_sim = ft.Column(); total_gastos_sim = [0]
        txt_gasto_sim = ft.TextField(label="Valor", width=100, on_change=formatar_moeda); lbl_total_gastos = ft.Text("Total: R$ 0,00", weight="bold")
        def add_gasto(e):
            try: v = float(txt_gasto_sim.value.replace(".","").replace(",", ".")); total_gastos_sim[0] += v; lista_gastos_sim.controls.append(ft.Text(f"+ R$ {v:.2f}", color="#00FF7F")); lbl_total_gastos.value = f"Total: R$ {total_gastos_sim[0]:.2f}"; txt_gasto_sim.value=""; page.update()
            except: pass
        def sub_gasto(e):
            try: v = float(txt_gasto_sim.value.replace(".","").replace(",", ".")); total_gastos_sim[0] -= v; lista_gastos_sim.controls.append(ft.Text(f"- R$ {v:.2f}", color="red")); lbl_total_gastos.value = f"Total: R$ {total_gastos_sim[0]:.2f}"; txt_gasto_sim.value=""; page.update()
            except: pass
        def limpar_gastos(e): total_gastos_sim[0] = 0; lista_gastos_sim.controls.clear(); lbl_total_gastos.value = "Total: R$ 0,00"; page.update()

        bloco_calc = ft.ExpansionTile(title=ft.Text("🧮 Calculadoras", weight="bold"), controls=[ft.Container(content=ft.Column([
                ft.Text("Troco"), ft.Row([txt_total_compra, txt_valor_pago, ft.ElevatedButton("Calcular", on_click=calc_troco, bgcolor="#007ACC", color="white")]), lbl_troco, ft.Divider(),
                ft.Text("Lista de Gastos"), ft.Row([txt_gasto_sim, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color="#00FF7F", on_click=add_gasto), ft.IconButton(ft.Icons.REMOVE_CIRCLE, icon_color="red", on_click=sub_gasto), ft.IconButton(ft.Icons.REFRESH, on_click=limpar_gastos)]), lbl_total_gastos, lista_gastos_sim
            ]), padding=10, bgcolor="#1A1A1A")])

        # 4. AGENDADOR (COM MÁSCARAS)
        txt_comando = ft.TextField(label="Diga ou Digite (Ex: Luz 150 dia 10)", hint_text="Microfone 🎤", expand=True, multiline=True, min_lines=1, max_lines=3)
        txt_nome = ft.TextField(label="Conta", expand=1, bgcolor="#111"); txt_data = ft.TextField(label="Venc.", width=100, bgcolor="#111", on_change=formatar_data); txt_valor = ft.TextField(label="Valor", width=100, bgcolor="#111", on_change=formatar_moeda)
        lbl_ia_msg = ft.Text("", color="yellow", size=12, italic=True)

        def processar_comando(e):
            if not txt_comando.value: return
            lbl_ia_msg.value = "Pensando..."; lbl_ia_msg.color = "cyan"; page.update()
            dados, erro = interpretar_comando_ia(txt_comando.value)
            if erro: lbl_ia_msg.value = "Offline."; lbl_ia_msg.color = "red"
            else:
                if dados.get("nome"): txt_nome.value = dados["nome"]
                if dados.get("valor"): 
                    v = float(dados["valor"])
                    txt_valor.value = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if dados.get("data"): txt_data.value = dados["data"]
                lbl_ia_msg.value = "🤖 Entendi!"; lbl_ia_msg.color = "#00FF7F"
            page.update()

        btn_ia = ft.IconButton(ft.Icons.AUTO_FIX_HIGH, icon_color="yellow", tooltip="IA Mágica (Preencher)", on_click=processar_comando)
        
        lista_lembretes = ft.Column(spacing=5)
        def render_l(pagos=False):
            lista_lembretes.controls.clear(); dados = listar_lembretes_filtro(pagos)
            if not dados: lista_lembretes.controls.append(ft.Text("Vazio.", color="grey")); page.update(); return
            for item in dados:
                cor = "#007ACC" if item[4]=="Pago" else ("#FF5555" if (datetime.strptime(item[2], "%d/%m/%Y") - datetime.now()).days < 0 else "#00FF7F")
                btn_agenda = ft.IconButton(ft.Icons.CALENDAR_MONTH, icon_color="white", tooltip="Google Agenda", on_click=lambda e, n=item[1], d=item[2], v=item[3]: abrir_google_agenda(e, n, d, v))
                acoes = [btn_agenda]
                if item[4]=="Pendente": acoes.append(ft.IconButton(ft.Icons.CHECK, icon_color="green", tooltip="Marcar Pago", on_click=lambda e, x=item[0]: (marcar_como_pago(x), att_l())))
                acoes.append(ft.IconButton(ft.Icons.DELETE, icon_color="red", tooltip="Excluir", on_click=lambda e, x=item[0]: (deletar_lembrete(x), att_l())))
                lista_lembretes.controls.append(ft.Container(content=ft.Row([ft.Column([ft.Text(item[1], weight="bold"), ft.Text(item[2], color=cor)]), ft.Row([ft.Text(f"R$ {item[3]:.2f}", size=16, weight="bold"), ft.Row(acoes)])], alignment="spaceBetween"), bgcolor="#1A1A1A", padding=10, border_radius=8, border=ft.Border(left=ft.BorderSide(4, cor))))
            page.update()
        def att_l(e=None): render_l(tab_h.bgcolor == "#007ACC")
        def add_l(e):
            try: 
                v = float(txt_valor.value.replace(".","").replace(",","."))
                criar_lembrete(txt_nome.value, txt_data.value, v)
                n, d = txt_nome.value, txt_data.value
                txt_nome.value=""; txt_valor.value=""; lbl_ia_msg.value=""; txt_comando.value=""; att_l()
                abrir_google_agenda(None, n, d, v)
            except: lbl_ia_msg.value="Erro dados."; page.update()

        tab_p = ft.ElevatedButton("A Pagar", on_click=lambda e: (setattr(tab_p, 'bgcolor', "#007ACC"), setattr(tab_h, 'bgcolor', "#222"), att_l()), bgcolor="#007ACC", color="white", expand=1)
        tab_h = ft.ElevatedButton("Histórico", on_click=lambda e: (setattr(tab_p, 'bgcolor', "#222"), setattr(tab_h, 'bgcolor', "#007ACC"), att_l()), bgcolor="#222", color="grey", expand=1)
        
        btn_pdf_agenda = ft.IconButton(ft.Icons.PICTURE_AS_PDF, icon_color="white", tooltip="Gerar PDF", on_click=lambda e: page.snack_bar(ft.Text("PDF Gerado!"))) # Placeholder
        
        att_l()

        # 5. SUPORTE IA
        txt_duvida = ft.TextField(label="Ajuda e Suporte", hint_text="Pergunte ao Finantea", expand=True)
        txt_resposta_ajuda = ft.Text("", size=12, italic=True)
        barra_ajuda = ft.ProgressBar(width=None, color="#007ACC", bgcolor="#222", visible=False)
        def enviar_duvida(e):
            if not txt_duvida.value: return
            btn_env.icon = ft.Icons.HOURGLASS_TOP; barra_ajuda.visible = True; page.update()
            txt_resposta_ajuda.value = f"🤖 {obter_ajuda_ia(txt_duvida.value)}"
            btn_env.icon = ft.Icons.SEND; barra_ajuda.visible = False; txt_duvida.value = ""; page.update()
        btn_env = ft.IconButton(ft.Icons.SEND, icon_color="#007ACC", tooltip="Enviar Pergunta", on_click=enviar_duvida)
        bloco_faq = ft.ExpansionTile(title=ft.Text("❓ Suporte & Dúvidas (IA)", weight="bold", color="grey"), controls=[ft.Container(content=ft.Column([ft.Row([txt_duvida, btn_env]), barra_ajuda, ft.Container(content=txt_resposta_ajuda, bgcolor="#222", padding=10, border_radius=5)]), padding=10, bgcolor="#1A1A1A")])

        return ft.Column([
            bloco_perfil, bloco_dicas, bloco_calc,
            ft.Divider(color="grey"),
            ft.Text("AGENDADOR INTELIGENTE", weight="bold", color="grey"),
            ft.Container(content=ft.Column([ft.Row([txt_comando, btn_ia], alignment="center"), lbl_ia_msg, ft.Row([txt_nome]), ft.Row([txt_data, txt_valor]), ft.ElevatedButton("Salvar & Abrir Agenda", on_click=add_l, bgcolor="#007ACC", color="white", width=400)]), padding=10, bgcolor="#111", border_radius=10),
            ft.Row([tab_p, tab_h], spacing=0), ft.Divider(height=1), lista_lembretes,
            ft.Divider(height=20, color="transparent"), bloco_faq
        ], expand=True, scroll="auto")

    # --- NAVEGAÇÃO / ROTEAMENTO ---
    def ir_para_app():
        bar.visible = True
        mudar(0)

    def mudar(idx):
        conteudo_principal.content = [tela_extrato, tela_cofrinho, tela_ferramentas][idx]()
        for i, b in enumerate([b1, b2, b3]): b.icon_color = "#007ACC" if i==idx else "grey"
        page.update()
    
    b1 = ft.IconButton(ft.Icons.LIST_ALT, tooltip="Extrato", on_click=lambda e: mudar(0))
    b2 = ft.IconButton(ft.Icons.SAVINGS, tooltip="Cofrinhos", on_click=lambda e: mudar(1))
    b3 = ft.IconButton(ft.Icons.CONSTRUCTION, tooltip="Ferramentas", on_click=lambda e: mudar(2))
    bar = ft.Container(content=ft.Row([ft.Column([b1, ft.Text("Extrato", size=10)]), ft.Column([b2, ft.Text("Cofre", size=10)]), ft.Column([b3, ft.Text("Ferramentas", size=10)])], alignment="spaceAround"), bgcolor="#111", padding=5, visible=False)

    page.add(ft.Stack([ft.Container(ft.Image(src="icon.png", opacity=0.05)), ft.Column([conteudo_principal, bar], expand=True)], expand=True))
    
    if is_intro_ok(): ir_para_app()
    else: conteudo_principal.content = tela_intro(); page.update()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")